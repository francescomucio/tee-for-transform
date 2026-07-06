"""
Test command implementation.
"""

import contextlib
from pathlib import Path

import typer

from t4t.cli.context import CommandContext
from t4t.cli.selection import ModelSelector
from t4t.engine.execution_engine import ExecutionEngine
from t4t.parser import ProjectParser
from t4t.testing import TestExecutor


def cmd_test(
    project_folder: str,
    vars: str | None = None,
    verbose: bool = False,
    select: list[str] | None = None,
    exclude: list[str] | None = None,
    env: str | None = None,
) -> None:
    """Execute the test command."""
    ctx = CommandContext(
        project_folder=project_folder,
        vars=vars,
        verbose=verbose,
        select=select,
        exclude=exclude,
        env=env,
    )
    ctx.echo_environment()

    try:
        typer.echo(f"Running tests for project: {project_folder}")
        ctx.print_variables_info()
        ctx.print_selection_info()

        # Step 1: Compile project to OTS modules
        typer.echo("\n" + "=" * 50)
        typer.echo("t4t: COMPILING PROJECT TO OTS MODULES")
        typer.echo("=" * 50)
        try:
            from t4t.compiler import compile_project

            compile_results = compile_project(
                project_folder=str(ctx.project_path),
                connection_config=ctx.config["connection"],
                variables=ctx.vars,
                project_config=ctx.config,
            )
            typer.echo(
                f"✅ Compilation complete: {compile_results['ots_modules_count']} OTS module(s)"
            )

            # Extract graph and execution order from compile results
            graph = compile_results.get("dependency_graph")
            execution_order = compile_results.get("execution_order", [])
            parsed_models = compile_results.get("parsed_models", {})

            if not graph or not execution_order:
                raise RuntimeError("Compilation did not return dependency graph or execution order")

            typer.echo(f"✅ Using dependency graph from compilation: {len(graph['nodes'])} nodes")
            typer.echo(f"   Execution order: {' -> '.join(execution_order)}")

        except Exception as e:
            typer.echo(f"❌ Compilation failed: {e}", err=True)
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
            typer.echo(f"Filtered to {len(parsed_models)} models")

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
                execution_engine.adapter, project_folder=str(ctx.project_path)
            )

            typer.echo("\n" + "=" * 50)
            typer.echo("EXECUTING TESTS")
            typer.echo("=" * 50)

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
            typer.echo("\nTest Results:")
            typer.echo(f"  Total tests: {test_results['total']}")
            typer.echo(f"  ✅ Passed: {test_results['passed']}")
            typer.echo(f"  ❌ Failed: {test_results['failed']}")

            if test_results["warnings"]:
                typer.echo(f"\n  ⚠️  Warnings ({len(test_results['warnings'])}):")
                for warning in test_results["warnings"]:
                    typer.echo(f"    - {warning}")

            if test_results["errors"]:
                typer.echo(f"\n  ❌ Errors ({len(test_results['errors'])}):")
                for error in test_results["errors"]:
                    typer.echo(f"    - {error}")

            # Show individual test results if verbose
            if ctx.verbose and test_results["test_results"]:
                typer.echo("\nDetailed Results:")
                for result in test_results["test_results"]:
                    typer.echo(f"  {result}")

            # Exit with error code if there are test errors
            if test_results["errors"]:
                typer.echo("\n❌ Test execution failed with errors", err=True)
                raise typer.Exit(1)
            elif test_results["warnings"]:
                typer.echo("\n⚠️  Test execution completed with warnings")
            else:
                typer.echo("\n✅ All tests passed!")

        finally:
            if execution_engine:
                execution_engine.disconnect()

    except Exception as e:
        ctx.handle_error(e)
