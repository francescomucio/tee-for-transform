"""
Debug command implementation.
"""

import typer

from tee.cli.context import CommandContext
from tee.engine.connection_manager import ConnectionManager
from tee.parser.core.project_parser import ProjectParser
from tee.parser.shared.constants import OUTPUT_FILES


def cmd_debug(
    project_folder: str,
    vars: str | None = None,
    verbose: bool = False,
) -> None:
    """Execute the debug command to test database connectivity."""
    ctx = CommandContext(
        project_folder=project_folder,
        vars=vars,
        verbose=verbose,
    )
    connection_manager = None

    try:
        typer.echo(f"Testing database connectivity for project: {project_folder}")
        ctx.print_variables_info()

        typer.echo("\n" + "=" * 50)
        typer.echo("DIMENSION REGISTRY (from model metadata)")
        typer.echo("=" * 50)
        try:
            parser = ProjectParser(
                project_folder=str(ctx.project_path),
                connection=ctx.config["connection"],
                variables=ctx.vars,
                project_config=ctx.config,
            )
            parser.collect_models()
            reg = parser.orchestrator.dimension_registry
            out_dir = ctx.project_path / "output"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / OUTPUT_FILES["dimension_registry"]
            parser.orchestrator.json_exporter.export_dimension_registry(reg, str(out_path))
            typer.echo(f"Wrote {len(reg)} entr(y/ies) to {out_path}")
            preview = sorted(reg.items())[:25]
            for k, v in preview:
                typer.echo(f"  {k} -> {v}")
            if len(reg) > 25:
                typer.echo(f"  ... and {len(reg) - 25} more (see JSON file)")
        except Exception as e:
            typer.echo(f"Could not build dimension registry: {e}", err=True)

        # Create unified connection manager
        connection_manager = ConnectionManager(
            project_folder=str(ctx.project_path),
            connection_config=ctx.config["connection"],
            variables=ctx.vars,
        )

        typer.echo("\n" + "=" * 50)
        typer.echo("DATABASE CONNECTION TEST")
        typer.echo("=" * 50)

        # Test connection
        if connection_manager.test_connection():
            typer.echo("✅ Database connection successful!")

            # Get database info
            db_info = connection_manager.get_database_info()
            if db_info:
                typer.echo("\nDatabase Information:")
                for key, value in db_info.items():
                    typer.echo(f"  {key}: {value}")

            # Test supported materializations
            typer.echo("\nSupported Materializations:")
            materializations = connection_manager.get_supported_materializations()
            for mat in materializations:
                typer.echo(f"  - {mat}")

            typer.echo("\n✅ All connectivity tests passed!")

        else:
            typer.echo("❌ Database connection failed!", err=True)
            typer.echo("Please check your connection configuration in project.toml", err=True)

    except Exception as e:
        ctx.handle_error(e)
    finally:
        # Cleanup
        if connection_manager:
            connection_manager.cleanup()
