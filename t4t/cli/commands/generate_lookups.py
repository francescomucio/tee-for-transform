"""
CLI command: generate lookup tables.
"""

from __future__ import annotations


import typer

from t4t.cli.context import CommandContext
from t4t.parser.output.lookup_generator import generate_lookups


def cmd_generate_lookups(
    project_folder: str,
    vars: str | None = None,
    verbose: bool = False,
    auto_resolve_level_conflicts: bool = False,
) -> None:
    """
    Generate lookup tables from hierarchical dimensions.

    Creates `lkp_<level>.sql` and `lkp_<level>.py` files (skipping existing ones).
    """
    ctx = CommandContext(
        project_folder=project_folder,
        vars=vars,
        verbose=verbose,
    )

    try:
        typer.echo(f"Generating lookups for project: {ctx.project_path}")
        created = generate_lookups(
            project_path=ctx.project_path,
            vars_dict=ctx.vars,
            auto_resolve_level_conflicts=auto_resolve_level_conflicts,
        )
        if created:
            typer.echo(f"  ✅ Created {len(created) // 2} lookup table(s)")
        else:
            typer.echo("  ℹ️  No lookups created (nothing to generate or files already exist)")
    except Exception as e:
        ctx.handle_error(e)
