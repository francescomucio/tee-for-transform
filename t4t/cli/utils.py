"""
CLI utility functions.

Pure, stateless utility functions used across CLI commands.
"""

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any


def parse_vars(vars_string: str | None) -> dict[str, Any]:
    """
    Parse variables string into a dictionary.

    Args:
        vars_string: Variables string in JSON format (None for empty)

    Returns:
        Dictionary containing parsed variables

    Raises:
        ValueError: If the string is not valid JSON
    """
    if not vars_string:
        return {}

    try:
        return json.loads(vars_string)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid variables format (must be valid JSON): {e}") from e


def load_project_config(
    project_folder: str,
    vars_dict: dict[str, Any] | None = None,
    env_name: str | None = None,
) -> dict[str, Any]:
    """
    Load project configuration from project.toml file and merge with variables.

    Requires ``[environments.*]`` sections — legacy ``[connection]`` is no
    longer supported.

    When *env_name* is provided, the connection config for that environment
    is loaded via ``DatabaseConfigManager`` (the single source of truth for
    config parsing) and stored under the ``"connection"`` key in the returned
    dict for backward compatibility with CLI commands.

    Args:
        project_folder: Path to the project folder
        vars_dict: Optional dictionary of variables to merge into config
        env_name: Optional environment name to extract connection config for

    Returns:
        Dictionary containing project configuration with variables merged

    Raises:
        FileNotFoundError: If project.toml is not found
        ValueError: If required configuration is missing
    """
    project_toml_path = Path(project_folder) / "project.toml"

    if not project_toml_path.exists():
        raise FileNotFoundError(f"project.toml not found in {project_folder}")

    # Use tomllib (Python 3.11+ built-in, required for Python 3.14+)
    import tomllib

    with open(project_toml_path, "rb") as f:
        config = tomllib.load(f)

    # Validate required configuration
    if "project_folder" not in config:
        raise ValueError("project.toml must contain 'project_folder' setting")

    if "environments" not in config:
        raise ValueError(
            "project.toml must contain at least one '[environments.*]' section "
            "(e.g. [environments.dev]) — legacy [connection] is no longer supported"
        )

    # Merge variables into config
    if vars_dict:
        config["vars"] = vars_dict

    # If env_name is provided, use DatabaseConfigManager as single source of truth
    if env_name:
        from t4t.engine.config import DatabaseConfigManager

        manager = DatabaseConfigManager(project_folder)
        adapter_config = manager.load_config(env_name)

        # Convert AdapterConfig to dict for backward compat with CLI commands
        # that expect config["connection"] to be a dict
        conn_dict = asdict(adapter_config)
        # Remove fields that aren't simple connection params
        conn_dict.pop("naming", None)
        conn_dict.pop("connections", None)
        conn_dict.pop("extra", None)
        # Filter out None values for cleaner dict
        conn_dict = {k: v for k, v in conn_dict.items() if v is not None}

        config["connection"] = conn_dict

    return config


def setup_logging(verbose: bool = False) -> None:
    """
    Set up logging configuration.

    Args:
        verbose: If True, set logging level to DEBUG, otherwise INFO
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s - %(name)s - %(message)s")
