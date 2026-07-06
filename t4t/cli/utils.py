"""
CLI utility functions.

Pure, stateless utility functions used across CLI commands.
"""

import json
import logging
from pathlib import Path
from typing import Any

from t4t.adapters.base.config import SECRET_KEYS, resolve_secret_ref


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

    When *env_name* is provided, the default environment config
    (``[environments.default]``) is merged with the specific environment
    config (``[environments.<env_name>]``) and stored under the ``"connection"``
    key in the returned dict for backward compatibility with CLI commands.

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

    # If env_name is provided, merge default + specific env into connection key
    if env_name:
        environments = config.get("environments", {})
        merged_conn: dict[str, Any] = {}

        # Start with [environments.default] connection
        default_env = environments.get("default", {})
        default_conn = default_env.get("connection", {})
        if isinstance(default_conn, dict):
            merged_conn.update(default_conn)

        # Merge specific environment connection on top
        specific_env = environments.get(env_name, {})
        specific_conn = specific_env.get("connection", {})
        if isinstance(specific_conn, dict):
            merged_conn.update(specific_conn)

        # Resolve secret references in the merged connection config
        for key in list(merged_conn.keys()):
            if key in SECRET_KEYS and isinstance(merged_conn[key], str):
                original = merged_conn[key]
                resolved = resolve_secret_ref(original)
                if resolved != original:
                    merged_conn[key] = resolved

        # Store as "connection" for backward compat
        config["connection"] = merged_conn

    return config


def setup_logging(verbose: bool = False) -> None:
    """
    Set up logging configuration.

    Args:
        verbose: If True, set logging level to DEBUG, otherwise INFO
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s - %(name)s - %(message)s")
