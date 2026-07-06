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
        env: str | None = None,
        allow_destructive: bool = False,
    ) -> None:
        """
        Initialize command context from parameters.

        Args:
            project_folder: Path to the project folder
            vars: Variables string (JSON format)
            verbose: Enable verbose output
            select: Selection patterns
            exclude: Exclusion patterns
            env: Environment name (e.g. "dev", "prod") — if provided, the
                 connection config for that environment is loaded into
                 ``config["connection"]``. Defaults to "dev" if not specified.
            allow_destructive: Allow destructive operations on protected environments
        """
        # Parse variables if provided
        self.vars = parse_vars(vars)

        # Load project configuration with environment merging
        # Default to "dev" environment if none specified
        resolved_env = env or "dev"
        self.config = load_project_config(project_folder, self.vars, env_name=resolved_env)

        # Detect if env was explicitly provided by the user
        self.env_explicit = env is not None
        self.env_name = resolved_env

        # Check if the resolved environment is protected
        self._check_protected_env(project_folder, resolved_env, env)

        # Set up logging
        self.verbose = verbose
        setup_logging(self.verbose)

        # Resolve project folder to absolute path
        self.project_path = Path(project_folder).resolve()

        # Extract selection criteria
        self.select_patterns = select
        self.exclude_patterns = exclude

        # Destructive operations flag
        self.allow_destructive = allow_destructive

    def _check_protected_env(
        self, project_folder: str, resolved_env: str, explicit_env: str | None
    ) -> None:
        """Check if the resolved environment is protected and refuse implicit selection."""
        import tomllib
        from pathlib import Path

        toml_path = Path(project_folder) / "project.toml"
        if not toml_path.exists():
            return

        with open(toml_path, "rb") as f:
            config = tomllib.load(f)

        environments = config.get("environments", {})
        env_config = environments.get(resolved_env, {})

        if not isinstance(env_config, dict):
            return

        protected = env_config.get("protected", False)
        if not protected:
            return

        # If env was resolved implicitly (not via --env), refuse
        if not explicit_env:
            import typer

            typer.echo(
                typer.style("Error: ", fg=typer.colors.RED, bold=True)
                + f"Environment '{resolved_env}' is protected and cannot be selected implicitly. "
                "Use --env to explicitly select it.",
                err=True,
            )
            raise typer.Exit(1)

    def is_protected_env(self) -> bool:
        """Check if the current environment is protected."""
        import tomllib
        from pathlib import Path

        toml_path = self.project_path / "project.toml"
        if not toml_path.exists():
            return False

        with open(toml_path, "rb") as f:
            config = tomllib.load(f)

        environments = config.get("environments", {})
        env_config = environments.get(self.env_name, {})
        if not isinstance(env_config, dict):
            return False
        return bool(env_config.get("protected", False))

    def check_destructive_operation(self) -> None:
        """Check if a destructive operation is allowed on a protected environment."""
        if self.is_protected_env() and not self.allow_destructive:
            import typer

            typer.echo(
                typer.style("Error: ", fg=typer.colors.RED, bold=True)
                + f"Environment '{self.env_name}' is protected. "
                "Use --allow-destructive to perform destructive operations.",
                err=True,
            )
            raise typer.Exit(1)

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
