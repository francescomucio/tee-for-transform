"""
CLI utility functions.

Pure, stateless utility functions used across CLI commands.
"""

import json
import logging
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
    project_folder: str, vars_dict: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Load project configuration from project.toml file and merge with variables.

    Args:
        project_folder: Path to the project folder
        vars_dict: Optional dictionary of variables to merge into config

    Returns:
        Dictionary containing project configuration with variables merged
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

    if "connection" not in config:
        raise ValueError("project.toml must contain 'connection' configuration")

    # Merge variables into config
    if vars_dict:
        config["vars"] = vars_dict

    return config


def setup_logging(verbose: bool = False) -> None:
    """
    Set up logging configuration.

    Args:
        verbose: If True, set logging level to DEBUG, otherwise INFO
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s - %(name)s - %(message)s")
