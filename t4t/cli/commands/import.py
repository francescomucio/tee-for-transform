"""
Import command implementation.

Handles importing projects from other formats (dbt, etc.) into t4t format.
"""

from pathlib import Path
from typing import Literal

import typer

# Type alias for output format
OutputFormat = Literal["t4t", "ots"]


def cmd_import(
    source_project_folder: str,
    target_project_folder: str,
    format: OutputFormat = "t4t",
    preserve_filenames: bool = False,
    validate_execution: bool = False,
    verbose: bool = False,
    dry_run: bool = False,
) -> None:
    """
    Import a project from another format (dbt, etc.) into t4t format.

    Args:
        source_project_folder: Path to the source project folder (e.g., dbt project)
        target_project_folder: Path where the imported t4t project will be created
        format: Output format - "t4t" (default) or "ots"
        preserve_filenames: Keep original file names instead of using final table names
        validate_execution: Run execution validation (requires database connection)
        verbose: Enable verbose output
        dry_run: Show what would be imported without actually importing
    """
    source_path = Path(source_project_folder).resolve()
    target_path = Path(target_project_folder).resolve()

    # Validate source path exists
    if not source_path.exists():
        error_msg = (
            typer.style("Error: ", fg=typer.colors.RED, bold=True)
            + f"Source project folder '{source_project_folder}' does not exist"
        )
        typer.echo(error_msg, err=True)
        raise typer.Exit(1)

    # Validate target path doesn't exist (unless dry run)
    if not dry_run and target_path.exists():
        error_msg = (
            typer.style("Error: ", fg=typer.colors.RED, bold=True)
            + f"Target project folder '{target_project_folder}' already exists"
        )
        typer.echo(error_msg, err=True)
        raise typer.Exit(1)

    try:
        # Detect project type
        from t4t.importer.detector import ProjectType, detect_project_type

        project_type = detect_project_type(source_path)

        if project_type == ProjectType.UNKNOWN:
            error_msg = (
                typer.style("Error: ", fg=typer.colors.RED, bold=True)
                + f"Could not detect project type in '{source_project_folder}'. "
                + "Supported types: dbt"
            )
            typer.echo(error_msg, err=True)
            raise typer.Exit(1)

        typer.echo(f"Detected project type: {project_type.value}")

        if dry_run:
            typer.echo("\n🔍 DRY RUN MODE - No files will be created")
            typer.echo(f"Would import from: {source_path}")
            typer.echo(f"Would create project at: {target_path}")
            typer.echo(f"Format: {format}")
            typer.echo(f"Preserve filenames: {preserve_filenames}")
            return

        # Import based on project type
        if project_type == ProjectType.DBT:
            from t4t.importer.dbt.importer import import_dbt_project

            typer.echo(f"\n📦 Importing dbt project from: {source_path}")
            typer.echo(f"📁 Creating t4t project at: {target_path}")

            import_dbt_project(
                source_path=source_path,
                target_path=target_path,
                output_format=format,
                preserve_filenames=preserve_filenames,
                validate_execution=validate_execution,
                verbose=verbose,
            )
        else:
            error_msg = (
                typer.style("Error: ", fg=typer.colors.RED, bold=True)
                + f"Import for project type '{project_type.value}' is not yet implemented"
            )
            typer.echo(error_msg, err=True)
            raise typer.Exit(1)

        typer.echo("\n✅ Import completed successfully!")
        typer.echo(f"   Check {target_path}/IMPORT_REPORT.md for details")

    except Exception as e:
        error_msg = typer.style("Error: ", fg=typer.colors.RED, bold=True) + f"Import failed: {e}"
        typer.echo(error_msg, err=True)
        if verbose:
            import traceback

            typer.echo(traceback.format_exc(), err=True)
        raise typer.Exit(1) from e
