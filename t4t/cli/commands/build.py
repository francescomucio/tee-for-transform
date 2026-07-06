"""
Build command implementation.

Builds models with interleaved test execution, stopping on test failures.
"""

import typer

from t4t.cli.context import CommandContext
from t4t.compiler import CompilationError
from t4t.engine.connection_manager import ConnectionManager
from t4t.executor import build_models
from t4t.parser.output.lookup_generator import generate_lookups
from t4t.state import prepare_retry_select_patterns


def _pluralize(count: int, singular: str, plural: str | None = None) -> str:
    """
    Pluralize a word based on count.

    Args:
        count: Number to check
        singular: Singular form of the word
        plural: Optional plural form (defaults to singular + 's')

    Returns:
        Plural form if count != 1, otherwise singular
    """
    if plural is None:
        plural = singular + "s"
    return plural if count != 1 else singular


def cmd_build(
    project_folder: str,
    vars: str | None = None,
    verbose: bool = False,
    select: list[str] | None = None,
    exclude: list[str] | None = None,
    retry: bool = False,
    auto_resolve_level_conflicts: bool = True,
    env: str | None = None,
) -> None:
    """Execute the build command."""
    ctx = CommandContext(
        project_folder=project_folder,
        vars=vars,
        verbose=verbose,
        select=select,
        exclude=exclude,
        env=env,
    )
    ctx.echo_environment()
    connection_manager = None

    try:
        typer.echo(f"Building project: {project_folder}")
        ctx.print_variables_info()
        ctx.print_selection_info()

        typer.echo("Refreshing generated lookup models...")
        generate_lookups(
            project_path=ctx.project_path,
            vars_dict=ctx.vars,
            auto_resolve_level_conflicts=auto_resolve_level_conflicts,
        )

        # Create unified connection manager
        connection_manager = ConnectionManager(
            project_folder=str(ctx.project_path),
            connection_config=ctx.config["connection"],
            variables=ctx.vars,
        )

        if retry and ctx.select_patterns:
            typer.echo(
                typer.style("Error: ", fg=typer.colors.RED, bold=True)
                + "Cannot use --retry together with --select.",
                err=True,
            )
            raise typer.Exit(1)

        select_patterns = ctx.select_patterns
        if retry:
            try:
                select_patterns = prepare_retry_select_patterns(
                    str(ctx.project_path),
                    ctx.config["connection"],
                    ctx.vars,
                    ctx.config,
                )
            except ValueError as e:
                typer.echo(
                    typer.style("Error: ", fg=typer.colors.RED, bold=True) + str(e),
                    err=True,
                )
                raise typer.Exit(1) from None
            except CompilationError as e:
                ctx.handle_error(e)

        # Build models with interleaved tests
        results = build_models(
            project_folder=str(ctx.project_path),
            connection_config=ctx.config["connection"],
            save_analysis=True,
            variables=ctx.vars,
            select_patterns=select_patterns,
            exclude_patterns=ctx.exclude_patterns,
            project_config=ctx.config,
            environment=ctx.env,
        )

        # Calculate statistics
        len(results["executed_tables"]) + len(results["failed_tables"])
        successful_count = len(results["executed_tables"])
        failed_count = len(results["failed_tables"])
        executed_functions = results.get("executed_functions", [])
        failed_functions = results.get("failed_functions", [])
        total_functions = len(executed_functions) + len(failed_functions)
        total_tests = results.get("test_results", {}).get("total", 0)
        passed_tests = results.get("test_results", {}).get("passed", 0)
        failed_tests = results.get("test_results", {}).get("failed", 0)

        # Build completion message
        parts = []
        if successful_count > 0:
            parts.append(f"{successful_count} {_pluralize(successful_count, 'table')}")
        if executed_functions:
            parts.append(
                f"{len(executed_functions)} {_pluralize(len(executed_functions), 'function')}"
            )

        if parts:
            typer.echo(f"\nCompleted! Successfully executed: {', '.join(parts)}")
        else:
            typer.echo("\nCompleted!")

        if total_functions > 0:
            typer.echo(
                f"  ✅ Successful: {successful_count} {_pluralize(successful_count, 'table')}, {len(executed_functions)} {_pluralize(len(executed_functions), 'function')}"
            )
        else:
            typer.echo(
                f"  ✅ Successful: {successful_count} {_pluralize(successful_count, 'table')}"
            )

        if failed_count > 0:
            typer.echo(f"  ❌ Failed: {failed_count} {_pluralize(failed_count, 'table')}")
        if failed_functions:
            typer.echo(
                f"  ❌ Failed: {len(failed_functions)} {_pluralize(len(failed_functions), 'function')}"
            )

        typer.echo(
            f"Tests: {passed_tests} passed, {failed_tests} failed out of {total_tests} total"
        )

        if failed_count > 0 or failed_tests > 0:
            if failed_count > 0:
                typer.echo(f"  ❌ Failed models: {failed_count}")
            if failed_tests > 0:
                typer.echo(f"  ❌ Failed tests: {failed_tests}")
            raise typer.Exit(1)
        else:
            typer.echo(
                f"  ✅ All {successful_count} {_pluralize(successful_count, 'table')} executed successfully!"
            )
            if executed_functions:
                typer.echo(
                    f"  ✅ All {len(executed_functions)} {_pluralize(len(executed_functions), 'function')} deployed successfully!"
                )
            typer.echo(f"  ✅ All {total_tests} tests passed!")

        if ctx.verbose:
            typer.echo(f"Analysis info: {results.get('analysis', {})}")

    except KeyboardInterrupt:
        typer.echo("\n\n⚠️  Build interrupted by user")
        raise typer.Exit(130) from None
    except Exception as e:
        ctx.handle_error(e)
    finally:
        # Cleanup
        if connection_manager:
            connection_manager.cleanup()
