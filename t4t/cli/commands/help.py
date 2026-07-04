"""
Help command implementation.
"""

import typer


def cmd_help(ctx: typer.Context) -> None:
    """Show help information."""
    # Show the same help as --help flag for consistency
    # Get the parent context (root app) to show main help, not command help
    parent_ctx = ctx.parent
    if parent_ctx:
        typer.echo(parent_ctx.get_help())
    else:
        # Fallback to current context if no parent (shouldn't happen)
        typer.echo(ctx.get_help())
