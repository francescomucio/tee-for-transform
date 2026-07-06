"""
t4t CLI Main Module

Command-line interface for the t4t SQL model execution framework.
"""

from typing import Any, Literal

import typer

from t4t.adapters import is_adapter_supported, list_available_adapters
from t4t.cli.commands import (
    cmd_build,
    cmd_compile,
    cmd_debug,
    cmd_docs,
    cmd_generate_lookups,
    cmd_help,
    cmd_import,
    cmd_init,
    cmd_run,
    cmd_seed,
    cmd_test,
)
from t4t.cli.commands import ots as ots_commands

# Type aliases for better type safety and IDE support
OutputFormat = Literal["json", "yaml"]
DatabaseType = Literal["duckdb", "snowflake", "postgresql", "bigquery", "motherduck"]


class AlphabeticalOrderGroup(typer.core.TyperGroup):
    """Custom Typer Group that lists commands in alphabetical order."""

    def list_commands(self, _ctx: typer.Context) -> list[str]:
        return sorted(self.commands.keys())


def validate_format(value: str) -> OutputFormat:
    """Validate format option (json or yaml)."""
    if value not in ["json", "yaml"]:
        raise typer.BadParameter(
            typer.style("Error: ", fg=typer.colors.RED, bold=True)
            + f"Invalid format '{value}'. Must be 'json' or 'yaml'."
        )
    return value  # type: ignore[return-value]


def validate_database_type(value: str) -> DatabaseType:
    """Validate database type option."""
    db_type = value.lower()
    # MotherDuck uses the duckdb adapter, so we need to handle it specially
    if db_type == "motherduck":
        return db_type  # type: ignore[return-value]
    if not is_adapter_supported(db_type):
        available = ", ".join(sorted(list_available_adapters()))
        raise typer.BadParameter(
            typer.style("Error: ", fg=typer.colors.RED, bold=True)
            + f"Unsupported database type '{db_type}'. "
            f"Supported: {available}, motherduck"
        )
    return db_type  # type: ignore[return-value]


# Create Typer app with alphabetical command ordering
app = typer.Typer(
    name="t4t",
    help="t4t - T(ee) for Transform (and t-shirts!)",
    add_completion=False,
    rich_markup_mode="rich",
    cls=AlphabeticalOrderGroup,
    invoke_without_command=True,
)


@app.callback()
def main_callback(ctx: typer.Context) -> None:
    """Main CLI callback - shows help when no command is provided."""
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


# Common option definitions to reduce duplication
PROJECT_FOLDER_ARG = typer.Argument(None, help="Path to the project folder containing project.toml")
VERBOSE_OPTION = typer.Option(False, "-v", "--verbose", help="Enable verbose output")
VARS_OPTION = typer.Option(None, "--vars", help="Variables to pass to models (JSON format)")
SELECT_OPTION = typer.Option(
    None, "-s", "--select", help="Select models. Can be used multiple times."
)
EXCLUDE_OPTION = typer.Option(
    None, "-e", "--exclude", help="Exclude models. Can be used multiple times."
)
RETRY_OPTION = typer.Option(
    False,
    "--retry",
    help="Re-run models that failed or were skipped downstream in the last run (same as run:failed+).",
)


def _check_required_argument(ctx: typer.Context, _arg_name: str, arg_value: Any) -> None:
    """Check if a required argument is provided, show help if not."""
    if arg_value is None:
        typer.echo(ctx.get_help())
        raise typer.Exit(0)


@app.command()
def run(
    ctx: typer.Context,
    project_folder: str | None = PROJECT_FOLDER_ARG,
    verbose: bool = VERBOSE_OPTION,
    vars: str | None = VARS_OPTION,
    select: list[str] | None = SELECT_OPTION,
    exclude: list[str] | None = EXCLUDE_OPTION,
    retry: bool = RETRY_OPTION,
    auto_resolve_level_conflicts: bool = typer.Option(
        True,
        "--auto-resolve-level-conflicts",
        help="Automatically resolve duplicate hierarchy level names as <dimension>_<level> during lookup generation.",
    ),
    env: str | None = typer.Option(
        None, "--env", help="Environment name (e.g. dev, prod). Defaults to 'dev'."
    ),
    allow_destructive: bool = typer.Option(
        False,
        "--allow-destructive",
        help="Allow destructive operations on protected environments.",
    ),
) -> None:
    """Parse and execute SQL models."""
    _check_required_argument(ctx, "project_folder", project_folder)
    cmd_run(
        project_folder=project_folder,
        vars=vars,
        verbose=verbose,
        select=select,
        exclude=exclude,
        retry=retry,
        auto_resolve_level_conflicts=auto_resolve_level_conflicts,
        env=env,
        allow_destructive=allow_destructive,
    )


@app.command()
def debug(
    ctx: typer.Context,
    project_folder: str | None = PROJECT_FOLDER_ARG,
    verbose: bool = VERBOSE_OPTION,
    vars: str | None = VARS_OPTION,
) -> None:
    """Test database connectivity and configuration."""
    _check_required_argument(ctx, "project_folder", project_folder)
    cmd_debug(
        project_folder=project_folder,
        vars=vars,
        verbose=verbose,
    )


@app.command()
def test(
    ctx: typer.Context,
    project_folder: str | None = PROJECT_FOLDER_ARG,
    verbose: bool = VERBOSE_OPTION,
    vars: str | None = VARS_OPTION,
    select: list[str] | None = SELECT_OPTION,
    exclude: list[str] | None = EXCLUDE_OPTION,
) -> None:
    """Run data quality tests on models."""
    _check_required_argument(ctx, "project_folder", project_folder)
    cmd_test(
        project_folder=project_folder,
        vars=vars,
        verbose=verbose,
        select=select,
        exclude=exclude,
    )


@app.command()
def build(
    ctx: typer.Context,
    project_folder: str | None = PROJECT_FOLDER_ARG,
    verbose: bool = VERBOSE_OPTION,
    vars: str | None = VARS_OPTION,
    select: list[str] | None = SELECT_OPTION,
    exclude: list[str] | None = EXCLUDE_OPTION,
    retry: bool = RETRY_OPTION,
    auto_resolve_level_conflicts: bool = typer.Option(
        True,
        "--auto-resolve-level-conflicts",
        help="Automatically resolve duplicate hierarchy level names as <dimension>_<level> during lookup generation.",
    ),
    env: str | None = typer.Option(
        None, "--env", help="Environment name (e.g. dev, prod). Defaults to 'dev'."
    ),
    allow_destructive: bool = typer.Option(
        False,
        "--allow-destructive",
        help="Allow destructive operations on protected environments.",
    ),
) -> None:
    """Build models with tests (stops on test failure)."""
    _check_required_argument(ctx, "project_folder", project_folder)
    cmd_build(
        project_folder=project_folder,
        vars=vars,
        verbose=verbose,
        select=select,
        exclude=exclude,
        retry=retry,
        auto_resolve_level_conflicts=auto_resolve_level_conflicts,
        env=env,
        allow_destructive=allow_destructive,
    )


@app.command()
def seed(
    ctx: typer.Context,
    project_folder: str | None = PROJECT_FOLDER_ARG,
    verbose: bool = VERBOSE_OPTION,
    vars: str | None = VARS_OPTION,
) -> None:
    """Load seed files (CSV, JSON, TSV) into database tables."""
    _check_required_argument(ctx, "project_folder", project_folder)
    cmd_seed(
        project_folder=project_folder,
        vars=vars,
        verbose=verbose,
    )


@app.command()
def init(
    ctx: typer.Context,
    project_name: str | None = typer.Argument(
        None, help="Name of the project (will create a folder with this name)"
    ),
    database_type: DatabaseType = typer.Option(
        "duckdb",
        "-d",
        "--database-type",
        help="Database type (duckdb, snowflake, postgresql, bigquery, motherduck)",
        callback=validate_database_type,
    ),
) -> None:
    """Initialize a new t4t project."""
    _check_required_argument(ctx, "project_name", project_name)
    cmd_init(
        project_name=project_name,
        database_type=database_type,
    )


@app.command()
def compile(
    ctx: typer.Context,
    project_folder: str | None = PROJECT_FOLDER_ARG,
    vars: str | None = VARS_OPTION,
    verbose: bool = VERBOSE_OPTION,
    format: OutputFormat = typer.Option(
        "json", "-f", "--format", help="Output format: json or yaml", callback=validate_format
    ),
) -> None:
    """Compile t4t project to OTS modules."""
    _check_required_argument(ctx, "project_folder", project_folder)
    cmd_compile(
        project_folder=project_folder,
        vars=vars,
        verbose=verbose,
        format=format,
    )


@app.command()
def docs(
    ctx: typer.Context,
    project_folder: str | None = PROJECT_FOLDER_ARG,
    vars: str | None = VARS_OPTION,
    verbose: bool = VERBOSE_OPTION,
    output_dir: str | None = typer.Option(
        None, "-o", "--output-dir", help="Output directory for docs (default: output/docs)"
    ),
    auto_resolve_level_conflicts: bool = typer.Option(
        True,
        "--auto-resolve-level-conflicts",
        help="Automatically resolve duplicate hierarchy level names as <dimension>_<level> during lookup generation.",
    ),
    skip_lookups: bool = typer.Option(
        False,
        "--skip-lookups",
        help="Skip lookup generation before building docs.",
    ),
    infer_dim_from_column_names: bool = typer.Option(
        False,
        "--infer-dim-from-column-names",
        help="Infer dimensional links from fact column names matching dimension/lookup primary keys.",
    ),
) -> None:
    """Generate static documentation site with dependency graph."""
    _check_required_argument(ctx, "project_folder", project_folder)
    cmd_docs(
        project_folder=project_folder,
        vars=vars,
        verbose=verbose,
        output_dir=output_dir,
        auto_resolve_level_conflicts=auto_resolve_level_conflicts,
        skip_lookups=skip_lookups,
        infer_dim_from_column_names=infer_dim_from_column_names,
    )


@app.command(name="generate-lookups")
def generate_lookups(
    ctx: typer.Context,
    project_folder: str | None = PROJECT_FOLDER_ARG,
    vars: str | None = VARS_OPTION,
    verbose: bool = VERBOSE_OPTION,
    auto_resolve_level_conflicts: bool = typer.Option(
        True,
        "--auto-resolve-level-conflicts",
        help="Automatically resolve duplicate hierarchy level names as <dimension>_<level>.",
    ),
) -> None:
    """Generate lookup tables from hierarchical dimensions."""
    _check_required_argument(ctx, "project_folder", project_folder)
    cmd_generate_lookups(
        project_folder=project_folder,
        vars=vars,
        verbose=verbose,
        auto_resolve_level_conflicts=auto_resolve_level_conflicts,
    )


@app.command()
def help(ctx: typer.Context) -> None:
    """Show help information."""
    cmd_help(ctx)


@app.command(name="import")
def import_cmd(
    _ctx: typer.Context,
    source_project_folder: str = typer.Argument(
        ..., help="Path to the source project folder to import"
    ),
    target_project_folder: str = typer.Argument(
        ..., help="Path where the imported t4t project will be created"
    ),
    format: Literal["t4t", "ots"] = typer.Option(
        "t4t", "-f", "--format", help="Output format: t4t or ots"
    ),
    preserve_filenames: bool = typer.Option(
        False,
        "--preserve-filenames",
        help="Keep original file names instead of using final table names",
    ),
    validate_execution: bool = typer.Option(
        False,
        "--validate-execution",
        help="Run execution validation (requires database connection)",
    ),
    verbose: bool = VERBOSE_OPTION,
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be imported without actually importing"
    ),
    keep_jinja: bool = typer.Option(
        False,
        "--keep-jinja",
        help="Keep Jinja2 templates in models (converts ref/source only). Note: Requires Jinja2 support in t4t (coming soon)",
    ),
    default_schema: str = typer.Option(
        "public",
        "--default-schema",
        help="Default schema name for models and functions (default: public)",
    ),
    target_dialect: str | None = typer.Option(
        None,
        "--target-dialect",
        help="Target database dialect for SQL conversion (e.g., postgresql, snowflake, duckdb). Defaults to PostgreSQL if not specified.",
    ),
    select: list[str] | None = SELECT_OPTION,
    exclude: list[str] | None = EXCLUDE_OPTION,
) -> None:
    """Import a project from another format (dbt, etc.) into t4t format."""
    cmd_import(
        source_project_folder=source_project_folder,
        target_project_folder=target_project_folder,
        format=format,
        preserve_filenames=preserve_filenames,
        validate_execution=validate_execution,
        verbose=verbose,
        dry_run=dry_run,
        keep_jinja=keep_jinja,
        default_schema=default_schema,
        target_dialect=target_dialect,
        select=select,
        exclude=exclude,
    )


# OTS command group with alphabetical ordering
ots_app = typer.Typer(
    name="ots",
    help="Open Transformation Specification (OTS) module commands",
    add_completion=False,
    invoke_without_command=True,
    cls=AlphabeticalOrderGroup,
)


@ots_app.callback()
def ots_callback(ctx: typer.Context) -> None:  # type: ignore[no-untyped-def]
    """Open Transformation Specification (OTS) module commands."""
    # If no subcommand was provided, show help
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


@ots_app.command("run")
def ots_run(
    ctx: typer.Context,
    ots_path: str | None = typer.Argument(
        None, help="Path to OTS module file (.ots.json) or directory"
    ),
    project_folder: str | None = typer.Option(
        None, "--project-folder", help="Project folder for connection config and merging"
    ),
    vars: str | None = VARS_OPTION,
    verbose: bool = VERBOSE_OPTION,
    select: list[str] | None = SELECT_OPTION,
    exclude: list[str] | None = EXCLUDE_OPTION,
) -> None:
    """Execute OTS modules."""
    _check_required_argument(ctx, "ots_path", ots_path)
    ots_commands.cmd_ots_run(
        ots_path=ots_path,
        project_folder=project_folder,
        vars=vars,
        verbose=verbose,
        select=select,
        exclude=exclude,
    )


@ots_app.command("validate")
def ots_validate(
    ctx: typer.Context,
    ots_path: str | None = typer.Argument(
        None, help="Path to OTS module file (.ots.json) or directory"
    ),
    verbose: bool = VERBOSE_OPTION,
) -> None:
    """Validate OTS modules."""
    _check_required_argument(ctx, "ots_path", ots_path)
    ots_commands.cmd_ots_validate(
        ots_path=ots_path,
        verbose=verbose,
    )


# Register OTS app as a subcommand
app.add_typer(ots_app)


def main() -> None:
    """Main CLI entry point."""
    app()


if __name__ == "__main__":
    main()
