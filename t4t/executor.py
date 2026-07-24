"""
t4t Executor

Handles the complete workflow of parsing and executing SQL models based on project configuration.
"""

import logging
from typing import TYPE_CHECKING, Any

from t4t.adapters.base.state_table import StateTableDDLError
from t4t.compiler import CompilationError, compile_project
from t4t.engine import ModelExecutor
from t4t.engine.config import is_env_protected
from t4t.engine.fingerprint import compute_project_fingerprints, store_project_fingerprints
from t4t.executor_helpers import build_helpers, shared_helpers
from t4t.parser import ProjectParser
from t4t.parser.shared.exceptions import ParserError
from t4t.state import create_state_backend, results_to_manifest, utc_now_iso
from t4t.state.warehouse_backend import WarehouseStateBackend

if TYPE_CHECKING:
    from t4t.adapters import AdapterConfig

# Constants for output formatting
SECTION_SEPARATOR = "=" * 50


def _try_persist_run_manifest(
    project_folder: str,
    results: dict[str, Any],
    command: str,
    started_at: str,
    *,
    connection_config: dict[str, Any] | AdapterConfig | None = None,
    project_config: dict[str, Any] | None = None,
    variables: dict[str, Any] | None = None,
    function_names: set[str] | None = None,
    cli_args: dict[str, Any] | None = None,
    environment: str | None = None,
    protected: bool = False,
    run_id: str | None = None,
    parsed_models: dict[str, Any] | None = None,
    dependency_graph: dict[str, Any] | None = None,
) -> None:
    """Persist the run manifest and fingerprints via the configured
    StateBackend (#20 step 6: `environments.<env>.state.backend`, default
    "local" -- `LocalStateBackend`, same as before this option existed).

    Also computes and stores each attempted model's fingerprint (#13 step 7):
    after the manifest is persisted, sql_hash/config_hash/fingerprint are
    written for every model that was *attempted* this run (status "success"
    or "failed" in the manifest -- i.e. selected and execution attempted),
    regardless of that model's own outcome. "skipped" nodes (never reached,
    e.g. downstream of a failure or excluded by selection) are not written.

    `parsed_models`/`dependency_graph` should be the project's full,
    unfiltered set -- even when `--select` narrowed what actually ran, direct
    upstream dependencies outside the selection still need their fingerprint
    computed to feed the hash chain, they're just not persisted here unless
    they were also attempted.

    Failure handling is asymmetric on purpose (#20 acceptance criterion 3):
    a `StateTableDDLError` (missing CREATE SCHEMA/CREATE TABLE permission
    under the warehouse backend) is deliberately let through -- the whole
    run must fail with that error, DDL text and all, not be swallowed into
    a warning. Every other failure (e.g. local disk issues, a warehouse
    connection blip) keeps the pre-existing best-effort "log only" behavior,
    matching `LocalStateBackend`'s own failure-tolerant precedent.
    """
    logger = logging.getLogger(__name__)
    try:
        from pathlib import Path

        finished_at = utc_now_iso()
        manifest = results_to_manifest(
            results,
            command,  # type: ignore[arg-type]
            str(Path(project_folder).resolve()),
            started_at,
            finished_at,
            project_config=project_config,
            variables=variables,
            cli_args=cli_args,
            function_names=function_names,
            environment=environment,
            protected=protected,
            run_id=run_id,
        )
        backend = create_state_backend(
            project_folder, connection_config or {}, env_name=environment
        )
        attempted = {n.name for n in manifest.nodes if n.status in ("success", "failed")}

        # Multi-schema partial-failure guard (#20 design decision): pre-create
        # every touched data schema's state table in one pass, before any
        # writes happen for this run, so a DDL failure on one schema fails
        # the whole run rather than leaving some models tracked and others
        # not.
        if isinstance(backend, WarehouseStateBackend) and attempted:
            backend.ensure_schemas_for_models(attempted)

        backend.append_run(manifest)

        if parsed_models and attempted:
            graph = dependency_graph or {}
            fingerprints = compute_project_fingerprints(parsed_models, graph)
            store_project_fingerprints(backend, fingerprints, model_names=attempted)
    except StateTableDDLError:
        raise
    except Exception as e:
        logger.warning("Could not persist run manifest: %s", e)


def execute_models(
    project_folder: str,
    connection_config: dict[str, Any] | AdapterConfig,
    save_analysis: bool = True,
    variables: dict[str, Any] | None = None,
    select_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    project_config: dict[str, Any] | None = None,
    env_name: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """
    Execute SQL models by compiling to OTS modules and running them in dependency order.

    This function handles the complete workflow:
    1. Compile project to OTS modules (if needed)
    2. Load OTS modules from output/ots_modules/
    3. Build dependency graph and determine execution order
    4. Execute models using the execution engine
    5. Optionally save analysis files

    Note: This function does NOT execute tests. Use `t4t test` or `t4t build` to run tests.

    Args:
        project_folder: Path to the project folder containing SQL models
        connection_config: Database connection configuration
        save_analysis: Whether to save parsing analysis to files
        variables: Optional variables for SQL substitution
        select_patterns: Optional list of patterns to select models
        exclude_patterns: Optional list of patterns to exclude models
        project_config: Optional project configuration
        run_id: Identity of this run, used to correlate model_started/finished
            events and the persisted run manifest. Generated here if not
            provided by the caller (e.g. direct/programmatic use, tests) --
            the CLI (`run.py`) always supplies one, generated at the very
            start of the command, so it is available for the first line of
            output.

    Returns:
        Dictionary containing execution results and analysis info
    """
    logger = logging.getLogger(__name__)
    if run_id is None:
        import uuid

        run_id = str(uuid.uuid4())

    # Diagnostic only (debug level, silent unless --verbose): the raw,
    # *unredacted* connection config is passed via extra -- JSONFormatter is
    # responsible for redacting it before serializing (see
    # t4t.observability.logging_setup.JSONFormatter / redact_secrets()).
    # Call sites are not expected to redact for themselves.
    _config_for_log = (
        connection_config
        if isinstance(connection_config, dict)
        else getattr(connection_config, "__dict__", {})
    )
    logger.debug(
        "Resolved connection configuration",
        extra={"connection_config": _config_for_log},
    )

    # Step 0: Compile project to OTS modules first
    logger.info(f"\n{SECTION_SEPARATOR}")
    logger.info("t4t: COMPILING PROJECT TO OTS MODULES")
    logger.info(SECTION_SEPARATOR)
    try:
        compile_results = compile_project(
            project_folder=project_folder,
            connection_config=connection_config,
            variables=variables,
            project_config=project_config,
        )
        logger.info(
            f"✅ Compilation complete: {compile_results['ots_modules_count']} OTS module(s)"
        )

        # Extract and validate graph and execution order from compile results
        graph, execution_order, parsed_models = shared_helpers.validate_compile_results(
            compile_results
        )
        run_started_at = utc_now_iso()
        fnames = set((compile_results.get("parsed_functions") or {}).keys())

    except (CompilationError, ParserError) as e:
        logger.error(f"Compilation failed: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during compilation: {e}")
        raise CompilationError(f"Compilation failed: {e}") from e

    # Handle case when there are no models
    if not parsed_models and not execution_order:
        logger.info(f"\n{SECTION_SEPARATOR}")
        logger.info("EXECUTION RESULTS")
        logger.info(SECTION_SEPARATOR)
        logger.info("\n✅ No models to execute")
        logger.info("   Project compiled successfully with 0 models")
        empty = shared_helpers.create_empty_execution_results(graph)
        _try_persist_run_manifest(
            project_folder,
            empty,
            "run",
            run_started_at,
            connection_config=connection_config,
            project_config=project_config,
            variables=variables,
            function_names=fnames or None,
            environment=env_name,
            protected=is_env_protected(project_folder, env_name),
            run_id=run_id,
            parsed_models=parsed_models,
            dependency_graph=graph,
        )
        return empty

    # Create parser instance for model execution (needed by ModelExecutor)
    parser = ProjectParser(project_folder, connection_config, variables, project_config)
    parser.parsed_models = parsed_models
    parser.graph = graph

    # Step 2.5: Apply selection filtering if specified
    filtered_parsed_models = None
    filtered_execution_order = None

    if select_patterns or exclude_patterns:
        from .cli.selection import ModelSelector

        selector = ModelSelector(select_patterns=select_patterns, exclude_patterns=exclude_patterns)
        original_count = len(parsed_models)
        filtered_parsed_models, filtered_execution_order = selector.filter_models(
            parsed_models, execution_order
        )
        filtered_count = len(filtered_parsed_models)

        logger.info(f"\nFiltered to {filtered_count} models (from {original_count} total)")
        if filtered_count > 0:
            logger.info(f"Filtered execution order: {' -> '.join(filtered_execution_order)}")
        else:
            logger.warning("⚠️  No models matched the selection criteria!")
            empty = shared_helpers.create_empty_execution_results(
                graph, warnings=["No models matched the selection criteria"]
            )
            _try_persist_run_manifest(
                project_folder,
                empty,
                "run",
                run_started_at,
                connection_config=connection_config,
                project_config=project_config,
                variables=variables,
                function_names=fnames or None,
                environment=env_name,
                protected=is_env_protected(project_folder, env_name),
                run_id=run_id,
                parsed_models=parsed_models,
                dependency_graph=graph,
            )
            return empty

    # Step 3: Execute models
    logger.info(f"\n{SECTION_SEPARATOR}")
    logger.info("EXECUTING SQL MODELS")
    logger.info(SECTION_SEPARATOR)

    model_executor = ModelExecutor(
        project_folder, connection_config, env_name=env_name, run_id=run_id
    )

    try:
        # Execute models using the executor (pass filtered models if selection was applied)
        results = model_executor.execute_models(
            parser,
            variables,
            parsed_models=filtered_parsed_models,
            execution_order=filtered_execution_order,
        )

        # Step 4: Save analysis files if requested (after execution to include qualified SQL)
        if save_analysis:
            parser.save_to_json()
            logger.info("Analysis files saved to output folder")

        # Print detailed results
        logger.info(f"\n{SECTION_SEPARATOR}")
        logger.info("EXECUTION RESULTS")
        logger.info(SECTION_SEPARATOR)

        if results.get("executed_functions"):
            logger.info("\nSuccessfully executed functions:")
            for function in results["executed_functions"]:
                logger.info(f"  - {function}")

        if results.get("failed_functions"):
            logger.warning("\nFailed functions:")
            for failure in results["failed_functions"]:
                logger.warning(f"  - {failure['function']}: {failure['error']}")

        if results["executed_tables"]:
            logger.info("\nSuccessfully executed tables:")
            for table in results["executed_tables"]:
                table_info = results["table_info"].get(table, {})
                row_count = table_info.get("row_count", 0)
                logger.info(f"  - {table}: {row_count} rows")

        if results["failed_tables"]:
            logger.warning("\nFailed tables:")
            for failure in results["failed_tables"]:
                logger.warning(f"  - {failure['table']}: {failure['error']}")

        # Get database info
        try:
            db_info = model_executor.get_database_info()
            if db_info:
                logger.info("\nDatabase Info:")
                logger.info(f"  Type: {db_info.get('connection_type', 'Unknown')}")
                logger.info(f"  Connected: {db_info.get('is_connected', False)}")
        except Exception as e:
            logger.warning(f"Could not get database info: {e}")
            # Don't fail execution if we can't get database info

        # Add analysis info to results (use filtered data if filtering was applied)
        final_models = filtered_parsed_models if filtered_parsed_models else parsed_models
        final_order = filtered_execution_order if filtered_execution_order else execution_order
        results["analysis"] = {
            "total_models": len(final_models),
            "total_tables": len(final_models),
            "execution_order": final_order,
            "dependency_graph": graph,
        }

        _try_persist_run_manifest(
            project_folder,
            results,
            "run",
            run_started_at,
            connection_config=connection_config,
            project_config=project_config,
            variables=variables,
            function_names=fnames or None,
            environment=env_name,
            protected=is_env_protected(project_folder, env_name),
            run_id=run_id,
            parsed_models=parsed_models,
            dependency_graph=graph,
        )
        return results

    except Exception as e:
        logger.error(f"Error during execution: {e}")
        raise


def build_models(
    project_folder: str,
    connection_config: dict[str, Any] | AdapterConfig,
    save_analysis: bool = True,
    variables: dict[str, Any] | None = None,
    select_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    project_config: dict[str, Any] | None = None,
    env_name: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """
    Build models with interleaved test execution, stopping on test failures.

    This function executes models and tests interleaved:
    1. Compile project to OTS modules (if needed)
    2. Load OTS modules and build dependency graph
    3. Execute a model
    4. Run its tests immediately
    5. If any ERROR severity test fails, stop execution
    6. Skip dependents of failed models

    Args:
        project_folder: Path to the project folder containing SQL models
        connection_config: Database connection configuration
        save_analysis: Whether to save parsing analysis to files
        variables: Optional variables for SQL substitution
        select_patterns: Optional list of patterns to select models
        exclude_patterns: Optional list of patterns to exclude models
        project_config: Optional project configuration
        run_id: Identity of this run (see `execute_models`'s docstring).
            Generated here if not provided by the caller.

    Returns:
        Dictionary containing execution results and analysis info

    Raises:
        SystemExit: If tests fail with ERROR severity
    """
    logger = logging.getLogger(__name__)
    if run_id is None:
        import uuid

        run_id = str(uuid.uuid4())

    logger.info(f"\n{SECTION_SEPARATOR}")
    logger.info("t4t: BUILDING MODELS WITH TESTS")
    logger.info(SECTION_SEPARATOR)

    # Step 1: Compile project to OTS modules first
    logger.info(f"\n{SECTION_SEPARATOR}")
    logger.info("t4t: COMPILING PROJECT TO OTS MODULES")
    logger.info(SECTION_SEPARATOR)
    try:
        compile_results = compile_project(
            project_folder=project_folder,
            connection_config=connection_config,
            variables=variables,
            project_config=project_config,
        )
        logger.info(
            f"✅ Compilation complete: {compile_results['ots_modules_count']} OTS module(s)"
        )

        # Extract and validate graph and execution order from compile results
        graph, execution_order, parsed_models = shared_helpers.validate_compile_results(
            compile_results
        )
        build_started_at = utc_now_iso()
        # Full, unfiltered project models -- kept separately because
        # setup_build_context_from_compile() below may reassign `parsed_models`
        # to a `--select`-filtered subset. Fingerprint computation always
        # needs the full set so direct dependencies outside the selection
        # still get a fingerprint to feed the hash chain (see
        # _try_persist_run_manifest's parsed_models/dependency_graph args).
        full_parsed_models = parsed_models

    except (CompilationError, ParserError) as e:
        logger.error(f"Compilation failed: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during compilation: {e}")
        raise CompilationError(f"Compilation failed: {e}") from e

    # Step 2: Set up build context using compile results
    parser, parsed_models, graph, execution_order = build_helpers.setup_build_context_from_compile(
        project_folder,
        connection_config,
        variables,
        select_patterns,
        exclude_patterns,
        project_config,
        parsed_models,
        graph,
        execution_order,
    )

    # Load seeds even if there are no models (seeds should load regardless)
    from t4t.engine import ModelExecutor
    from t4t.engine.execution_engine import ExecutionEngine

    temp_executor = ModelExecutor(
        project_folder, connection_config, env_name=env_name, run_id=run_id
    )
    temp_executor.execution_engine = ExecutionEngine(
        temp_executor.config, project_folder=project_folder, variables=variables
    )
    temp_executor.execution_engine.connect()

    seed_results = {"loaded_tables": [], "failed_tables": [], "total_seeds": 0}
    try:
        seed_results = build_helpers._load_seeds_for_build(temp_executor, project_folder)
    finally:
        temp_executor.execution_engine.disconnect()

    # Handle case when there are no models
    if not parsed_models and not execution_order:
        logger.info(f"\n{SECTION_SEPARATOR}")
        logger.info("BUILD RESULTS")
        logger.info(SECTION_SEPARATOR)
        logger.info("\n✅ No models to build")
        logger.info("   Project compiled successfully with 0 models")
        if seed_results["total_seeds"] > 0:
            logger.info(f"  Seeds loaded: {len(seed_results['loaded_tables'])}")
            if seed_results["failed_tables"]:
                logger.warning(f"  Seeds failed: {len(seed_results['failed_tables'])}")
        empty_results = shared_helpers.create_empty_build_results(graph)
        empty_results["seed_results"] = seed_results
        _try_persist_run_manifest(
            project_folder,
            empty_results,
            "build",
            build_started_at,
            connection_config=connection_config,
            project_config=project_config,
            variables=variables,
            function_names=None,
            environment=env_name,
            protected=is_env_protected(project_folder, env_name),
            run_id=run_id,
            parsed_models=full_parsed_models,
            dependency_graph=graph,
        )
        return empty_results

    # Step 2: Initialize executors
    logger.info(f"\n{SECTION_SEPARATOR}")
    logger.info("BUILDING MODELS AND TESTS")
    logger.info(SECTION_SEPARATOR)

    model_executor = None
    failed_models = set()
    skipped_models: dict[str, str] = {}
    all_test_results = []

    try:
        model_executor, test_executor = build_helpers.initialize_build_executors(
            project_folder,
            connection_config,
            variables,
            load_seeds=False,
            env_name=env_name,
            run_id=run_id,
        )

        # Evaluate Python models before execution
        parsed_models = parser.orchestrator.evaluate_python_models(
            parsed_models, variables=variables
        )

        # Step 2.5: Execute functions before models
        # Functions must be created before models that depend on them
        parsed_functions, function_results = build_helpers.execute_functions_in_build(
            parser,
            model_executor,
            test_executor,
            execution_order,
            failed_models,
            skipped_models,
            all_test_results,
        )

        # Step 3: Execute models and tests interleaved
        build_helpers.execute_models_with_tests(
            execution_order,
            parsed_models,
            parsed_functions,
            graph,
            model_executor,
            test_executor,
            parser,
            failed_models,
            skipped_models,
            all_test_results,
        )

        # Step 4: Save analysis files if requested
        if save_analysis:
            parser.save_to_json()
            logger.info("\nAnalysis files saved to output folder")

        # Step 5: Compile and return results
        results = build_helpers.compile_build_results(
            execution_order,
            failed_models,
            skipped_models,
            all_test_results,
            parsed_models,
            graph,
            parsed_functions,
            function_results,
            seed_results,
        )
        build_helpers.print_build_summary(results, failed_models, skipped_models)

        fn_build = set((parsed_functions or {}).keys()) if parsed_functions else set()
        _try_persist_run_manifest(
            project_folder,
            results,
            "build",
            build_started_at,
            connection_config=connection_config,
            project_config=project_config,
            variables=variables,
            function_names=fn_build or None,
            environment=env_name,
            protected=is_env_protected(project_folder, env_name),
            run_id=run_id,
            parsed_models=full_parsed_models,
            dependency_graph=graph,
        )
        return results

    except SystemExit:
        raise
    except Exception as e:
        logger.error(f"Error during build: {e}")
        raise
    finally:
        # Always disconnect
        if model_executor and model_executor.execution_engine:
            model_executor.execution_engine.disconnect()
