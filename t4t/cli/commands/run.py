"""
Run command implementation.
"""

import logging
import time
import uuid
from importlib.metadata import PackageNotFoundError, version

import typer

from t4t.cli.context import CommandContext
from t4t.engine.connection_manager import ConnectionManager
from t4t.executor import execute_models
from t4t.parser.output.lookup_generator import generate_lookups

logger = logging.getLogger(__name__)

# #14: --retry is sugar for --select run:failed+ -- one implementation
# (ModelSelector's run:failed atomic condition + trailing-+ downstream
# modifier), not a second parallel "compute retry set" mechanism. See
# t4t/cli/selection.py and t4t/state/graph_walk.py.
_RETRY_SELECT_PATTERN = "run:failed+"


def _t4t_version() -> str:
    try:
        return version("t4t")
    except PackageNotFoundError:
        return "0.0.0"


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
    log_format: str = "text",
) -> None:
    """Execute the run command."""
    # run_id is generated here, at the very start, so it can be threaded
    # through execute_models()/ModelExecutor and stamped on every event this
    # invocation emits, including the very first one (run_started) — it must
    # not be minted later (e.g. only when the run manifest is built).
    run_id = str(uuid.uuid4())
    run_start_time = time.monotonic()

    try:
        ctx = CommandContext(
            project_folder=project_folder,
            vars=vars,
            verbose=verbose,
            select=select,
            exclude=exclude,
            env=env,
            log_format=log_format,
        )
    except ValueError as e:
        typer.echo(
            typer.style("Error: ", fg=typer.colors.RED, bold=True) + str(e),
            err=True,
        )
        raise typer.Exit(1) from None
    connection_manager = None
    run_finished_emitted = False

    try:
        if ctx.is_protected_env():
            logger.info(f"⚠️  PROTECTED ENVIRONMENT: {ctx.env_name}")
        # This is also the run_started lifecycle event: run_id must be the
        # first thing t4t emits about this invocation.
        logger.info(
            f"Running t4t on project: {project_folder}",
            extra={
                "type": "run_started",
                "run_id": run_id,
                "env": ctx.env_name,
                "t4t_version": _t4t_version(),
                "selection": ctx.select_patterns,
            },
        )
        ctx.print_variables_info()
        ctx.print_selection_info()

        logger.info("Refreshing generated lookup models...")
        generate_lookups(
            project_path=ctx.project_path,
            vars_dict=ctx.vars,
            auto_resolve_level_conflicts=auto_resolve_level_conflicts,
            env_name=ctx.env_name,
        )

        # Create unified connection manager
        connection_manager = ConnectionManager(
            project_folder=str(ctx.project_path),
            connection_config=ctx.config["connection"],
            variables=ctx.vars,
            env_name=ctx.env_name,
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
            select_patterns = [_RETRY_SELECT_PATTERN]

        # Inject _naming_config into connection_config so it reaches the executor
        connection_config = ctx.config["connection"]
        naming_config = ctx.config.get("_naming_config")
        if naming_config:
            if isinstance(connection_config, dict):
                connection_config = {**connection_config, "_naming_config": naming_config}
            elif hasattr(connection_config, "naming") and connection_config.naming is None:
                connection_config.naming = naming_config

        # Execute models using the unified connection manager
        results = execute_models(
            project_folder=str(ctx.project_path),
            connection_config=connection_config,
            save_analysis=True,
            variables=ctx.vars,
            select_patterns=select_patterns,
            exclude_patterns=ctx.exclude_patterns,
            project_config=ctx.config,
            env_name=ctx.env_name,
            run_id=run_id,
        )

        # Calculate statistics
        successful_tables = len(results["executed_tables"])
        failed_tables = len(results["failed_tables"])

        executed_functions = results.get("executed_functions", [])
        failed_functions = results.get("failed_functions", [])
        successful_functions = len(executed_functions)
        failed_functions_count = len(failed_functions)

        warning_count = len(results.get("warnings", []))

        # Build completion message
        parts = []
        if successful_tables > 0:
            parts.append(f"{successful_tables} {_pluralize(successful_tables, 'table')}")
        if successful_functions > 0:
            parts.append(f"{successful_functions} {_pluralize(successful_functions, 'function')}")

        status = "success" if failed_tables == 0 and failed_functions_count == 0 else "failed"
        duration_ms = int((time.monotonic() - run_start_time) * 1000)

        # This is also the run_finished lifecycle event -- the run's last line.
        completion_extra = {
            "type": "run_finished",
            "run_id": run_id,
            "status": status,
            "duration_ms": duration_ms,
            "executed_tables": successful_tables,
            "failed_tables": failed_tables,
        }
        if parts:
            logger.info(
                f"\nCompleted! Successfully executed: {', '.join(parts)}", extra=completion_extra
            )
        else:
            logger.info("\nCompleted!", extra=completion_extra)
        run_finished_emitted = True

        # Show failures if any
        if failed_tables > 0 or failed_functions_count > 0 or warning_count > 0:
            if successful_tables > 0 or successful_functions > 0:
                logger.info(
                    f"  ✅ Successful: {successful_tables} {_pluralize(successful_tables, 'table')}, {successful_functions} {_pluralize(successful_functions, 'function')}"
                )
            if failed_tables > 0:
                logger.warning(f"  ❌ Failed: {failed_tables} {_pluralize(failed_tables, 'table')}")
            if failed_functions_count > 0:
                logger.warning(
                    f"  ❌ Failed: {failed_functions_count} {_pluralize(failed_functions_count, 'function')}"
                )
            if warning_count > 0:
                logger.warning(
                    f"  ⚠️  Warnings: {warning_count} {_pluralize(warning_count, 'warning')}"
                )
        elif successful_tables > 0 or successful_functions > 0:
            # All successful
            if successful_tables > 0:
                logger.info(
                    f"  ✅ All {successful_tables} {_pluralize(successful_tables, 'table')} executed successfully!"
                )
            if successful_functions > 0:
                logger.info(
                    f"  ✅ All {successful_functions} {_pluralize(successful_functions, 'function')} deployed successfully!"
                )

        if ctx.verbose:
            logger.info(f"Analysis info: {results.get('analysis', {})}")

    except KeyboardInterrupt:
        typer.echo("\n\n⚠️  Run interrupted by user")
        raise typer.Exit(130) from None
    except Exception as e:
        ctx.handle_error(e)
    finally:
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
        # Cleanup
        if connection_manager:
            connection_manager.cleanup()
