"""
Seed command implementation.
"""

import typer

from t4t.cli.context import CommandContext
from t4t.engine.execution_engine import ExecutionEngine
from t4t.engine.seeds import SeedDiscovery, SeedLoader


def cmd_seed(
    project_folder: str,
    vars: str | None = None,
    verbose: bool = False,
) -> None:
    """Execute the seed command to load seed files into the database."""
    ctx = CommandContext(
        project_folder=project_folder,
        vars=vars,
        verbose=verbose,
    )

    try:
        typer.echo(f"Loading seeds from project: {project_folder}")

        # Get seeds folder
        seeds_folder = ctx.project_path / "seeds"

        if not seeds_folder.exists():
            typer.echo(f"⚠️  Seeds folder not found: {seeds_folder}")
            typer.echo("   Create a 'seeds' folder in your project to use this feature.")
            return

        # Discover seed files
        seed_discovery = SeedDiscovery(seeds_folder)
        seed_files = seed_discovery.discover_seed_files()

        if not seed_files:
            typer.echo("ℹ️  No seed files found in seeds folder")
            typer.echo("   Supported formats: CSV, TSV, JSON")
            typer.echo("   Example: seeds/users.csv or seeds/my_schema/orders.json")
            return

        typer.echo(f"\nFound {len(seed_files)} seed file(s):")
        for file_path, schema_name in seed_files:
            if schema_name:
                typer.echo(
                    f"  - {file_path.relative_to(seeds_folder)} → {schema_name}.{file_path.stem}"
                )
            else:
                typer.echo(f"  - {file_path.relative_to(seeds_folder)} → {file_path.stem}")

        # Create execution engine to get adapter
        execution_engine = ExecutionEngine(
            ctx.config["connection"], project_folder=str(ctx.project_path), variables=ctx.vars
        )

        try:
            # Connect to database
            execution_engine.connect()
            typer.echo(f"\nConnected to database: {execution_engine.adapter.config.type}")

            # Load seeds
            typer.echo("\nLoading seeds...")
            seed_loader = SeedLoader(execution_engine.adapter)
            seed_results = seed_loader.load_all_seeds(seed_files)

            # Print results
            typer.echo("\n" + "=" * 50)
            typer.echo("SEED LOADING RESULTS")
            typer.echo("=" * 50)

            if seed_results["loaded_tables"]:
                typer.echo(
                    f"\n✅ Successfully loaded {len(seed_results['loaded_tables'])} seed(s):"
                )
                for table in seed_results["loaded_tables"]:
                    # Get table info to show row count
                    try:
                        table_info = execution_engine.adapter.get_table_info(table)
                        row_count = table_info.get("row_count", 0)
                        typer.echo(f"  - {table}: {row_count} rows")
                    except Exception as e:
                        typer.echo(f"  - {table} (could not get row count: {e})")

            if seed_results["failed_tables"]:
                typer.echo(
                    f"\n❌ Failed to load {len(seed_results['failed_tables'])} seed(s):", err=True
                )
                for failure in seed_results["failed_tables"]:
                    typer.echo(f"  - {failure['file']}: {failure['error']}", err=True)

            if not seed_results["failed_tables"]:
                typer.echo("\n✅ All seeds loaded successfully!")

        finally:
            execution_engine.disconnect()

    except Exception as e:
        ctx.handle_error(e)
