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
    project_folder: str,
    vars_dict: dict[str, Any] | None = None,
    env_name: str | None = None,
) -> dict[str, Any]:
    """
    Load project configuration from project.toml file and merge with variables.

    Args:
        project_folder: Path to the project folder
        vars_dict: Optional dictionary of variables to merge into config
        env_name: Optional environment name to load connection from [environments.<name>]

    Returns:
        Dictionary containing project configuration with variables merged

    Raises:
        ValueError: If the environment name is unknown
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

    # If env_name is specified, load connection from [environments.<env_name>]
    if env_name is not None:
        environments = config.get("environments", {})
        if not isinstance(environments, dict) or env_name not in environments:
            available = (
                ", ".join(sorted(environments.keys())) if isinstance(environments, dict) else ""
            )
            msg = f"Unknown environment '{env_name}'"
            if available:
                msg += f". Available environments: {available}"
            raise ValueError(msg)

        env_section = environments[env_name]
        if not isinstance(env_section, dict):
            raise ValueError(f"Environment '{env_name}' must be a table section")

        # Load connection from [environments.<name>].connection
        env_connection = env_section.get("connection", {})
        if isinstance(env_connection, dict):
            config["connection"] = env_connection

        # Merge env-level variables with CLI vars (CLI wins)
        env_variables = env_section.get("variables", {})
        if isinstance(env_variables, dict):
            merged_vars = dict(env_variables)
            if vars_dict:
                merged_vars.update(vars_dict)
            config["vars"] = merged_vars
        elif vars_dict:
            config["vars"] = vars_dict
    else:
        # Legacy mode: require [connection]
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
