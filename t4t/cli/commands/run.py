"""
Run command implementation.
"""

import typer

from t4t.cli.context import CommandContext
from t4t.compiler import CompilationError
from t4t.engine.connection_manager import ConnectionManager
from t4t.executor import execute_models
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


def cmd_run(
    project_folder: str,
    vars: str | None = None,
    verbose: bool = False,
    select: list[str] | None = None,
    exclude: list[str] | None = None,
    retry: bool = False,
    auto_resolve_level_conflicts: bool = True,
    env: str | None = None,
    allow_destructive: bool = False,
) -> None:
    """Execute the run command."""
    ctx = CommandContext(
        project_folder=project_folder,
        vars=vars,
        verbose=verbose,
        select=select,
        exclude=exclude,
        env=env,
        allow_destructive=allow_destructive,
    )
    connection_manager = None

    try:
        if ctx.is_protected_env():
            typer.echo(
                typer.style("⚠️  PROTECTED ENVIRONMENT", fg=typer.colors.YELLOW, bold=True)
                + f": {ctx.env_name}"
            )

        typer.echo(f"Running t4t on project: {project_folder}")
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
                    env_name=ctx.env_name,
                )
            except ValueError as e:
                typer.echo(
                    typer.style("Error: ", fg=typer.colors.RED, bold=True) + str(e),
                    err=True,
                )
                raise typer.Exit(1) from None
            except CompilationError as e:
                ctx.handle_error(e)

        # Execute models using the unified connection manager
        results = execute_models(
            project_folder=str(ctx.project_path),
            connection_config=ctx.config["connection"],
            save_analysis=True,
            variables=ctx.vars,
            select_patterns=select_patterns,
            exclude_patterns=ctx.exclude_patterns,
            project_config=ctx.config,
            env_name=ctx.env_name,
        )

        # Calculate statistics
        len(results["executed_tables"]) + len(results["failed_tables"])
        successful_tables = len(results["executed_tables"])
        failed_tables = len(results["failed_tables"])

        executed_functions = results.get("executed_functions", [])
        failed_functions = results.get("failed_functions", [])
        len(executed_functions) + len(failed_functions)
        successful_functions = len(executed_functions)
        failed_functions_count = len(failed_functions)

        warning_count = len(results.get("warnings", []))

        # Build completion message
        parts = []
        if successful_tables > 0:
            parts.append(f"{successful_tables} {_pluralize(successful_tables, 'table')}")
        if successful_functions > 0:
            parts.append(f"{successful_functions} {_pluralize(successful_functions, 'function')}")

        if parts:
            typer.echo(f"\nCompleted! Successfully executed: {', '.join(parts)}")
        else:
            typer.echo("\nCompleted!")

        # Show failures if any
        if failed_tables > 0 or failed_functions_count > 0 or warning_count > 0:
            if successful_tables > 0 or successful_functions > 0:
                typer.echo(
                    f"  ✅ Successful: {successful_tables} {_pluralize(successful_tables, 'table')}, {successful_functions} {_pluralize(successful_functions, 'function')}"
                )
            if failed_tables > 0:
                typer.echo(f"  ❌ Failed: {failed_tables} {_pluralize(failed_tables, 'table')}")
            if failed_functions_count > 0:
                typer.echo(
                    f"  ❌ Failed: {failed_functions_count} {_pluralize(failed_functions_count, 'function')}"
                )
            if warning_count > 0:
                typer.echo(f"  ⚠️  Warnings: {warning_count} {_pluralize(warning_count, 'warning')}")
        elif successful_tables > 0 or successful_functions > 0:
            # All successful
            if successful_tables > 0:
                typer.echo(
                    f"  ✅ All {successful_tables} {_pluralize(successful_tables, 'table')} executed successfully!"
                )
            if successful_functions > 0:
                typer.echo(
                    f"  ✅ All {successful_functions} {_pluralize(successful_functions, 'function')} deployed successfully!"
                )

        if ctx.verbose:
            typer.echo(f"Analysis info: {results.get('analysis', {})}")

    except Exception as e:
        ctx.handle_error(e)
    finally:
        # Cleanup
        if connection_manager:
            connection_manager.cleanup()
