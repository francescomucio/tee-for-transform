"""
Compile command implementation.
"""

from typing import Literal

import typer

from t4t.cli.context import CommandContext
from t4t.compiler import CompilationError, compile_project

# Type alias for output format
OutputFormat = Literal["json", "yaml"]


def cmd_compile(
    project_folder: str,
    vars: str | None = None,
    verbose: bool = False,
    format: OutputFormat = "json",
) -> None:
    """
    Compile t4t project to OTS modules.

    This command:
    1. Parses SQL/Python models
    2. Loads and validates imported OTS modules
    3. Detects conflicts
    4. Merges and converts to OTS format
    5. Validates compiled modules
    6. Exports to output/ots_modules/

    Args:
        project_folder: Path to the project folder
        vars: Optional variables for SQL substitution (JSON format)
        verbose: Enable verbose output
        format: Output format ("json" or "yaml")
    """
    ctx = CommandContext(
        project_folder=project_folder,
        vars=vars,
        verbose=verbose,
    )

    try:
        typer.echo(f"Compiling project: {project_folder}")
        ctx.print_variables_info()

        # Compile project
        results = compile_project(
            project_folder=str(ctx.project_path),
            connection_config=ctx.config["connection"],
            variables=ctx.vars,
            project_config=ctx.config,
            format=format,
        )

        typer.echo("\n✅ Compilation complete!")
        typer.echo(f"   Parsed models: {results['parsed_models_count']}")
        typer.echo(f"   Imported OTS: {results['imported_ots_count']}")
        typer.echo(f"   Total transformations: {results['total_transformations']}")
        typer.echo(f"   OTS modules: {results['ots_modules_count']}")
        typer.echo(f"   Output: {results['output_folder']}")

    except CompilationError as e:
        typer.echo(f"\n❌ Compilation failed: {e}", err=True)
        ctx.handle_error(e)
    except Exception as e:
        typer.echo(f"\n❌ Unexpected error: {e}", err=True)
        ctx.handle_error(e)
