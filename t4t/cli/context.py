"""
Command context for shared setup across CLI commands.
"""

from pathlib import Path

import typer

from .utils import load_project_config, parse_vars, setup_logging


class CommandContext:
    """
    Shared context for CLI commands.

    Handles common setup: parsing variables, loading config, setting up logging,
    and extracting selection criteria.
    """

    def __init__(
        self,
        project_folder: str,
        vars: str | None = None,
        verbose: bool = False,
        select: list[str] | None = None,
        exclude: list[str] | None = None,
    ) -> None:
        """
        Initialize command context from parameters.

        Args:
            project_folder: Path to the project folder
            vars: Variables string (JSON format)
            verbose: Enable verbose output
            select: Selection patterns
            exclude: Exclusion patterns
        """
        # Parse variables if provided
        self.vars = parse_vars(vars)

        # Load project configuration
        self.config = load_project_config(project_folder, self.vars)

        # Set up logging
        self.verbose = verbose
        setup_logging(self.verbose)

        # Resolve project folder to absolute path
        self.project_path = Path(project_folder).resolve()

        # Extract selection criteria
        self.select_patterns = select
        self.exclude_patterns = exclude

    def handle_error(self, error: Exception, show_traceback: bool = None) -> None:
        """
        Handle errors consistently across commands.

        Args:
            error: The exception that occurred
            show_traceback: Whether to show traceback (defaults to verbose mode)
        """
        if show_traceback is None:
            show_traceback = self.verbose

        # Use rich formatting for error messages
        error_prefix = typer.style("Error: ", fg=typer.colors.RED, bold=True)
        typer.echo(f"{error_prefix}{error}", err=True)
        if show_traceback:
            import traceback

            traceback.print_exc()
        raise typer.Exit(1)

    def print_variables_info(self) -> None:
        """Print variables information if verbose or if variables are set."""
        if self.vars:
            if self.verbose:
                typer.echo(f"Variables: {self.vars}")
            typer.echo(f"Using variables: {self.vars}")

    def print_selection_info(self) -> None:
        """Print selection criteria information if verbose."""
        if self.verbose:
            if self.select_patterns:
                typer.echo(f"Selection criteria: {self.select_patterns}")
            if self.exclude_patterns:
                typer.echo(f"Exclusion criteria: {self.exclude_patterns}")
