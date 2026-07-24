"""
Test command implementation.
"""

import contextlib
import logging
import time
import uuid
from pathlib import Path

import typer

from t4t.cli.context import CommandContext
from t4t.cli.selection import ModelSelector
from t4t.engine.execution_engine import ExecutionEngine
from t4t.parser import ProjectParser
from t4t.testing import TestExecutor

logger = logging.getLogger(__name__)


def cmd_test(
    project_folder: str,
    vars: str | None = None,
    verbose: bool = False,
    select: list[str] | None = None,
    exclude: list[str] | None = None,
    log_format: str = "text",
) -> None:
    """Execute the test command."""
    run_id = str(uuid.uuid4())
    run_start_time = time.monotonic()
    run_finished_emitted = False

    ctx = CommandContext(
        project_folder=project_folder,
        vars=vars,
        verbose=verbose,
        select=select,
        exclude=exclude,
        log_format=log_format,
    )

    try:
        logger.info(
            f"Running tests for project: {project_folder}",
            extra={
                "type": "run_started",
                "run_id": run_id,
                "env": ctx.env_name,
                "selection": ctx.select_patterns,
            },
        )
        ctx.print_variables_info()
        ctx.print_selection_info()

        # Step 1: Compile project to OTS modules
        logger.info("\n" + "=" * 50)
        logger.info("t4t: COMPILING PROJECT TO OTS MODULES")
        logger.info("=" * 50)
        try:
            from t4t.compiler import compile_project

            compile_results = compile_project(
                project_folder=str(ctx.project_path),
                connection_config=ctx.config["connection"],
                variables=ctx.vars,
                project_config=ctx.config,
            )
            logger.info(
                f"✅ Compilation complete: {compile_results['ots_modules_count']} OTS module(s)"
            )

            # Extract graph and execution order from compile results
            graph = compile_results.get("dependency_graph")
            execution_order = compile_results.get("execution_order", [])
            parsed_models = compile_results.get("parsed_models", {})

            if not graph or not execution_order:
                raise RuntimeError("Compilation did not return dependency graph or execution order")

            logger.info(f"✅ Using dependency graph from compilation: {len(graph['nodes'])} nodes")
            logger.info(f"   Execution order: {' -> '.join(execution_order)}")

        except Exception as e:
            logger.error(f"❌ Compilation failed: {e}")
            raise

        # Step 2: Create parser instance for test execution
        parser = ProjectParser(
            str(ctx.project_path), ctx.config["connection"], ctx.vars, ctx.config
        )
        parser.parsed_models = parsed_models
        parser.graph = graph

        # Apply selection filtering if specified
        if ctx.select_patterns or ctx.exclude_patterns:
            selector = ModelSelector(
                select_patterns=ctx.select_patterns, exclude_patterns=ctx.exclude_patterns
            )

            parsed_models, execution_order = selector.filter_models(parsed_models, execution_order)
            logger.info(f"Filtered to {len(parsed_models)} models")

        # Create model executor and initialize execution engine to get adapter
        # Resolve relative paths in connection config relative to project folder
        connection_config = ctx.config["connection"].copy()
        if "path" in connection_config and connection_config["path"]:
            db_path = Path(connection_config["path"])
            if not db_path.is_absolute():
                connection_config["path"] = str(ctx.project_path / db_path)

        execution_engine = ExecutionEngine(
            config=connection_config, project_folder=str(ctx.project_path), variables=ctx.vars
        )

        try:
            # Connect adapter
            execution_engine.connect()

            # Create test executor (discover SQL tests from tests/ folder)
            test_executor = TestExecutor(
                execution_engine.adapter, project_folder=str(ctx.project_path), run_id=run_id
            )

            logger.info("\n" + "=" * 50)
            logger.info("EXECUTING TESTS")
            logger.info("=" * 50)

            # Get parsed functions if available; functions may not be
            # available, in which case continue with model tests only
            parsed_functions = {}
            with contextlib.suppress(Exception):
                parsed_functions = ctx.parser.orchestrator.discover_and_parse_functions()

            # Execute all tests (both models and functions)
            test_results = test_executor.execute_all_tests(
                parsed_models=parsed_models,
                parsed_functions=parsed_functions,
                execution_order=execution_order,
            )

            # Print test results
            logger.info("\nTest Results:")
            logger.info(f"  Total tests: {test_results['total']}")
            logger.info(f"  ✅ Passed: {test_results['passed']}")
            logger.info(f"  ❌ Failed: {test_results['failed']}")

            if test_results["warnings"]:
                logger.warning(f"\n  ⚠️  Warnings ({len(test_results['warnings'])}):")
                for warning in test_results["warnings"]:
                    logger.warning(f"    - {warning}")

            if test_results["errors"]:
                logger.error(f"\n  ❌ Errors ({len(test_results['errors'])}):")
                for error in test_results["errors"]:
                    logger.error(f"    - {error}")

            # Show individual test results if verbose
            if ctx.verbose and test_results["test_results"]:
                logger.info("\nDetailed Results:")
                for result in test_results["test_results"]:
                    logger.info(f"  {result}")

            # Exit with error code if there are test errors -- the final
            # message on each branch also carries the run_finished event.
            if test_results["errors"]:
                logger.error(
                    "\n❌ Test execution failed with errors",
                    extra={"type": "run_finished", "run_id": run_id, "status": "failed"},
                )
                run_finished_emitted = True
                raise typer.Exit(1)
            elif test_results["warnings"]:
                logger.warning(
                    "\n⚠️  Test execution completed with warnings",
                    extra={"type": "run_finished", "run_id": run_id, "status": "warning"},
                )
                run_finished_emitted = True
            else:
                logger.info(
                    "\n✅ All tests passed!",
                    extra={"type": "run_finished", "run_id": run_id, "status": "success"},
                )
                run_finished_emitted = True

        finally:
            if execution_engine:
                execution_engine.disconnect()

    except Exception as e:
        ctx.handle_error(e)
    finally:
        # Guarantees run_finished fires even if an exception happened before
        # reaching one of the three normal-completion branches above (e.g.
        # compile_project() failing) -- same run_finished_emitted + finally
        # pattern as run.py/build.py.
        if not run_finished_emitted:
            duration_ms = int((time.monotonic() - run_start_time) * 1000)
            logger.info(
                "Run failed",
                extra={
                    "type": "run_finished",
                    "run_id": run_id,
                    "status": "error",
                    "duration_ms": duration_ms,
                },
            )
