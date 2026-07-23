"""
Build command implementation.

Builds models with interleaved test execution, stopping on test failures.
"""

import logging
import time
import uuid
from importlib.metadata import PackageNotFoundError, version

import typer

from t4t.cli.context import CommandContext
from t4t.compiler import CompilationError
from t4t.engine.connection_manager import ConnectionManager
from t4t.executor import build_models
from t4t.parser.output.lookup_generator import generate_lookups
from t4t.state import prepare_retry_select_patterns

logger = logging.getLogger(__name__)


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


def cmd_build(
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
    """Execute the build command."""
    # run_id is generated here, at the very start, so it can be threaded
    # through build_models()/ModelExecutor and stamped on every event this
    # invocation emits, including the very first one (run_started).
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
            f"Building project: {project_folder}",
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

        # Build models with interleaved tests
        results = build_models(
            project_folder=str(ctx.project_path),
            connection_config=ctx.config["connection"],
            save_analysis=True,
            variables=ctx.vars,
            select_patterns=select_patterns,
            exclude_patterns=ctx.exclude_patterns,
            project_config=ctx.config,
            env_name=ctx.env_name,
            run_id=run_id,
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

        status = "success" if failed_count == 0 and failed_tests == 0 else "failed"
        duration_ms = int((time.monotonic() - run_start_time) * 1000)
        completion_extra = {
            "type": "run_finished",
            "run_id": run_id,
            "status": status,
            "duration_ms": duration_ms,
            "executed_tables": successful_count,
            "failed_tables": failed_count,
        }

        # This is also the run_finished lifecycle event -- the run's last line.
        if parts:
            logger.info(
                f"\nCompleted! Successfully executed: {', '.join(parts)}", extra=completion_extra
            )
        else:
            logger.info("\nCompleted!", extra=completion_extra)
        run_finished_emitted = True

        if total_functions > 0:
            logger.info(
                f"  ✅ Successful: {successful_count} {_pluralize(successful_count, 'table')}, {len(executed_functions)} {_pluralize(len(executed_functions), 'function')}"
            )
        else:
            logger.info(
                f"  ✅ Successful: {successful_count} {_pluralize(successful_count, 'table')}"
            )

        if failed_count > 0:
            logger.warning(f"  ❌ Failed: {failed_count} {_pluralize(failed_count, 'table')}")
        if failed_functions:
            logger.warning(
                f"  ❌ Failed: {len(failed_functions)} {_pluralize(len(failed_functions), 'function')}"
            )

        logger.info(
            f"Tests: {passed_tests} passed, {failed_tests} failed out of {total_tests} total"
        )

        if failed_count > 0 or failed_tests > 0:
            if failed_count > 0:
                logger.warning(f"  ❌ Failed models: {failed_count}")
            if failed_tests > 0:
                logger.warning(f"  ❌ Failed tests: {failed_tests}")
            raise typer.Exit(1)
        else:
            logger.info(
                f"  ✅ All {successful_count} {_pluralize(successful_count, 'table')} executed successfully!"
            )
            if executed_functions:
                logger.info(
                    f"  ✅ All {len(executed_functions)} {_pluralize(len(executed_functions), 'function')} deployed successfully!"
                )
            logger.info(f"  ✅ All {total_tests} tests passed!")

        if ctx.verbose:
            logger.info(f"Analysis info: {results.get('analysis', {})}")

    except KeyboardInterrupt:
        typer.echo("\n\n⚠️  Build interrupted by user")
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
