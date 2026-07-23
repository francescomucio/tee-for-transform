"""
Command context for shared setup across CLI commands.
"""

from pathlib import Path

import typer

from t4t.observability import configure_logging

from .utils import load_project_config, parse_vars


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
        log_format: str = "text",
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
            log_format: "text" (default) or "json" — see
                 ``t4t.observability.logging_setup`` for the format registry.
        """
        # Parse variables if provided
        self.vars = parse_vars(vars)

        # Load project configuration with environment merging
        # Default to "dev" environment if none specified
        resolved_env = env or "dev"
        self.config = load_project_config(project_folder, self.vars, env_name=resolved_env)

        # Validate that the resolved environment exists in project config
        environments = self.config.get("environments", {})
        if resolved_env not in environments:
            available = sorted(environments.keys())
            raise ValueError(
                f"Environment '{resolved_env}' not found in project.toml. "
                f"Available environments: {available}"
            )

        # Detect if env was explicitly provided by the user
        self.env_explicit = env is not None
        self.env_name = resolved_env

        # Check if the resolved environment is protected
        self._check_protected_env(project_folder, resolved_env, env)

        # Set up logging: a single call. configure_logging() installs both
        # the legacy basicConfig-based stderr diagnostic handler (as its own
        # first step, via _install_legacy_root_handler) and the new stdout
        # text/json CLI output stream (t4t.observability), in that order,
        # so the stderr-deduplication filter always has a handler to attach
        # to -- no cross-function call-order dependency for a caller to get
        # wrong. See t4t.observability.logging_setup.configure_logging.
        self.verbose = verbose
        self.log_format = log_format
        configure_logging(log_format, self.verbose)

        # Resolve project folder to absolute path
        self.project_path = Path(project_folder).resolve()

        # Extract selection criteria
        self.select_patterns = select
        self.exclude_patterns = exclude

    def _check_protected_env(
        self, project_folder: str, resolved_env: str, explicit_env: str | None
    ) -> None:
        """Check if the resolved environment is protected and refuse implicit selection.

        Raises:
            ValueError: If the environment is protected and was selected implicitly.
        """
        from t4t.engine.config import is_env_protected

        if not is_env_protected(project_folder, resolved_env):
            return

        # If env was resolved implicitly (not via --env), refuse
        if not explicit_env:
            raise ValueError(
                f"Environment '{resolved_env}' is protected and cannot be selected implicitly. "
                "Use --env to explicitly select it."
            )

    def is_protected_env(self) -> bool:
        """Check if the current environment is protected."""
        from t4t.engine.config import is_env_protected

        return is_env_protected(str(self.project_path), self.env_name)

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
