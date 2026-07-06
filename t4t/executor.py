"""
t4t Executor

Handles the complete workflow of parsing and executing SQL models based on project configuration.
"""

import logging
from typing import TYPE_CHECKING, Any

from t4t.compiler import CompilationError, compile_project
from t4t.engine import ModelExecutor
from t4t.engine.config import is_env_protected
from t4t.executor_helpers import build_helpers, shared_helpers
from t4t.parser import ProjectParser
from t4t.parser.shared.exceptions import ParserError
from t4t.state import LocalStateBackend, results_to_manifest, utc_now_iso

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
    project_config: dict[str, Any] | None = None,
    variables: dict[str, Any] | None = None,
    function_names: set[str] | None = None,
    cli_args: dict[str, Any] | None = None,
    environment: str | None = None,
    protected: bool = False,
) -> None:
    """Write last_run.json and append to runs.sqlite; failures are logged only."""
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
        )
        backend = LocalStateBackend(Path(project_folder) / "output", env_name=environment)
        backend.append_run(manifest)
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

    Returns:
        Dictionary containing execution results and analysis info
    """
    logger = logging.getLogger(__name__)

    # Step 0: Compile project to OTS modules first
    print(f"\n{SECTION_SEPARATOR}")
    print("t4t: COMPILING PROJECT TO OTS MODULES")
    print(SECTION_SEPARATOR)
    try:
        compile_results = compile_project(
            project_folder=project_folder,
            connection_config=connection_config,
            variables=variables,
            project_config=project_config,
        )
        print(f"✅ Compilation complete: {compile_results['ots_modules_count']} OTS module(s)")

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
        print(f"\n{SECTION_SEPARATOR}")
        print("EXECUTION RESULTS")
        print(SECTION_SEPARATOR)
        print("\n✅ No models to execute")
        print("   Project compiled successfully with 0 models")
        empty = shared_helpers.create_empty_execution_results(graph)
        _try_persist_run_manifest(
            project_folder,
            empty,
            "run",
            run_started_at,
            project_config=project_config,
            variables=variables,
            function_names=fnames or None,
            environment=env_name,
            protected=is_env_protected(project_folder, env_name),
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

        print(f"\nFiltered to {filtered_count} models (from {original_count} total)")
        if filtered_count > 0:
            print(f"Filtered execution order: {' -> '.join(filtered_execution_order)}")
        else:
            print("⚠️  No models matched the selection criteria!")
            empty = shared_helpers.create_empty_execution_results(
                graph, warnings=["No models matched the selection criteria"]
            )
            _try_persist_run_manifest(
                project_folder,
                empty,
                "run",
                run_started_at,
                project_config=project_config,
                variables=variables,
                function_names=fnames or None,
                environment=env_name,
                protected=is_env_protected(project_folder, env_name),
            )
            return empty

    # Step 3: Execute models
    print(f"\n{SECTION_SEPARATOR}")
    print("EXECUTING SQL MODELS")
    print(SECTION_SEPARATOR)

    model_executor = ModelExecutor(project_folder, connection_config)

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
            print("Analysis files saved to output folder")

        # Print detailed results
        print(f"\n{SECTION_SEPARATOR}")
        print("EXECUTION RESULTS")
        print(SECTION_SEPARATOR)

        if results.get("executed_functions"):
            print("\nSuccessfully executed functions:")
            for function in results["executed_functions"]:
                print(f"  - {function}")

        if results.get("failed_functions"):
            print("\nFailed functions:")
            for failure in results["failed_functions"]:
                print(f"  - {failure['function']}: {failure['error']}")

        if results["executed_tables"]:
            print("\nSuccessfully executed tables:")
            for table in results["executed_tables"]:
                table_info = results["table_info"].get(table, {})
                row_count = table_info.get("row_count", 0)
                print(f"  - {table}: {row_count} rows")

        if results["failed_tables"]:
            print("\nFailed tables:")
            for failure in results["failed_tables"]:
                print(f"  - {failure['table']}: {failure['error']}")

        # Get database info
        try:
            db_info = model_executor.get_database_info()
            if db_info:
                print("\nDatabase Info:")
                print(f"  Type: {db_info.get('connection_type', 'Unknown')}")
                print(f"  Connected: {db_info.get('is_connected', False)}")
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
            project_config=project_config,
            variables=variables,
            function_names=fnames or None,
            environment=env_name,
            protected=is_env_protected(project_folder, env_name),
        )
        return results

    except Exception as e:
        print(f"Error during execution: {e}")
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

    Returns:
        Dictionary containing execution results and analysis info

    Raises:
        SystemExit: If tests fail with ERROR severity
    """
    logger = logging.getLogger(__name__)

    print(f"\n{SECTION_SEPARATOR}")
    print("t4t: BUILDING MODELS WITH TESTS")
    print(SECTION_SEPARATOR)

    # Step 1: Compile project to OTS modules first
    print(f"\n{SECTION_SEPARATOR}")
    print("t4t: COMPILING PROJECT TO OTS MODULES")
    print(SECTION_SEPARATOR)
    try:
        compile_results = compile_project(
            project_folder=project_folder,
            connection_config=connection_config,
            variables=variables,
            project_config=project_config,
        )
        print(f"✅ Compilation complete: {compile_results['ots_modules_count']} OTS module(s)")

        # Extract and validate graph and execution order from compile results
        graph, execution_order, parsed_models = shared_helpers.validate_compile_results(
            compile_results
        )
        build_started_at = utc_now_iso()

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

    temp_executor = ModelExecutor(project_folder, connection_config)
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
        print(f"\n{SECTION_SEPARATOR}")
        print("BUILD RESULTS")
        print(SECTION_SEPARATOR)
        print("\n✅ No models to build")
        print("   Project compiled successfully with 0 models")
        if seed_results["total_seeds"] > 0:
            print(f"  Seeds loaded: {len(seed_results['loaded_tables'])}")
            if seed_results["failed_tables"]:
                print(f"  Seeds failed: {len(seed_results['failed_tables'])}")
        empty_results = shared_helpers.create_empty_build_results(graph)
        empty_results["seed_results"] = seed_results
        _try_persist_run_manifest(
            project_folder,
            empty_results,
            "build",
            build_started_at,
            project_config=project_config,
            variables=variables,
            function_names=None,
            environment=env_name,
            protected=is_env_protected(project_folder, env_name),
        )
        return empty_results

    # Step 2: Initialize executors
    print(f"\n{SECTION_SEPARATOR}")
    print("BUILDING MODELS AND TESTS")
    print(SECTION_SEPARATOR)

    model_executor = None
    failed_models = set()
    skipped_models: dict[str, str] = {}
    all_test_results = []

    try:
        model_executor, test_executor = build_helpers.initialize_build_executors(
            project_folder, connection_config, variables, load_seeds=False
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
            print("\nAnalysis files saved to output folder")

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
            project_config=project_config,
            variables=variables,
            function_names=fn_build or None,
            environment=env_name,
            protected=is_env_protected(project_folder, env_name),
        )
        return results

    except SystemExit:
        raise
    except Exception as e:
        print(f"Error during build: {e}")
        raise
    finally:
        # Always disconnect
        if model_executor and model_executor.execution_engine:
            model_executor.execution_engine.disconnect()
