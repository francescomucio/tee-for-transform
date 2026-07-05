"""
Database configuration management.

This module handles loading database configurations from pyproject.toml
and environment variables with proper precedence and validation.
"""

import logging
import os
import tomllib
from pathlib import Path
from typing import Any

from t4t.adapters.base import AdapterConfig


class DatabaseConfigManager:
    """Manages database configurations from multiple sources."""

    def __init__(self, project_root: str | None = None) -> None:
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.logger = logging.getLogger(self.__class__.__name__)

    def load_config(
        self, config_name: str = "default", env_name: str | None = None
    ) -> AdapterConfig:
        """
        Load database configuration from pyproject.toml and environment variables.

        Args:
            config_name: Name of the configuration to load (default: "default")
            env_name: Optional environment name to load from [environments.<name>]

        Returns:
            AdapterConfig object with merged configuration

        Raises:
            ValueError: If configuration is invalid or missing
        """
        # Load from pyproject.toml
        toml_config = self._load_toml_config(config_name, env_name)

        # Load from environment variables
        env_config = self._load_env_config()

        # Merge configurations (env vars override toml)
        merged_config = self._merge_configs(toml_config, env_config)

        # Validate and create AdapterConfig
        return self._create_adapter_config(merged_config)

    def _load_toml_config(self, config_name: str, env_name: str | None = None) -> dict[str, Any]:
        """Load configuration from pyproject.toml or project.toml.

        Args:
            config_name: Name of the database configuration (for legacy tool.t4t.databases)
            env_name: Optional environment name to load from [environments.<name>]

        Returns:
            Dictionary containing the merged configuration
        """
        # Try pyproject.toml first
        toml_file = self.project_root / "pyproject.toml"
        if not toml_file.exists():
            # Fall back to project.toml
            toml_file = self.project_root / "project.toml"
            if not toml_file.exists():
                self.logger.debug("No pyproject.toml or project.toml found")
                return {}

        try:
            with open(toml_file, "rb") as f:
                data = tomllib.load(f)

            # Look for [tool.t4t.database], [tool.t4t.databases], or [connection]
            t4t_config = data.get("tool", {}).get("t4t", {})

            # Start with flags if they exist
            config: dict[str, Any] = {}
            if "flags" in data:
                config["extra"] = {"flags": data["flags"]}

            # If an env_name is specified, look in [environments.<env_name>]
            if env_name is not None:
                environments = data.get("environments", {})
                if not isinstance(environments, dict) or env_name not in environments:
                    available = (
                        ", ".join(sorted(environments.keys()))
                        if isinstance(environments, dict)
                        else ""
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
                    config.update(env_connection)

                # Load variables from [environments.<name>].variables
                env_variables = env_section.get("variables", {})
                if isinstance(env_variables, dict):
                    config["_env_variables"] = env_variables

                # Load protected flag
                config["_protected"] = env_section.get("protected", False)

                return config

            # Check for single database config in tool.t4t.database
            if "database" in t4t_config:
                config.update(t4t_config["database"])
                return config

            # Check for multiple database configs in tool.t4t.databases
            databases = t4t_config.get("databases", {})
            if isinstance(databases, dict) and config_name in databases:
                config.update(databases[config_name])
                return config

            # Check for legacy [connection] section
            if "connection" in data:
                self.logger.debug("Using legacy [connection] section")
                config.update(data["connection"])
                return config

            self.logger.debug(f"No database configuration '{config_name}' found in TOML file")
            return {}

        except ValueError:
            raise
        except Exception as e:
            self.logger.warning(f"Could not read pyproject.toml: {e}")
            return {}

    def _load_env_config(self) -> dict[str, Any]:
        """Load configuration from environment variables."""
        env_config = {}

        # Map environment variables to config keys
        env_mappings = {
            "T4T_DB_TYPE": "type",
            "T4T_DB_HOST": "host",
            "T4T_DB_PORT": "port",
            "T4T_DB_DATABASE": "database",
            "T4T_DB_USER": "user",
            "T4T_DB_PASSWORD": "password",
            "T4T_DB_PATH": "path",
            "T4T_DB_SCHEMA": "schema",
            "T4T_DB_WAREHOUSE": "warehouse",
            "T4T_DB_ROLE": "role",
            "T4T_DB_PROJECT": "project",
            "T4T_DB_SOURCE_DIALECT": "source_dialect",
            "T4T_DB_TARGET_DIALECT": "target_dialect",
        }

        # Load T4T_ prefixed variables
        for env_var, config_key in env_mappings.items():
            value = os.getenv(env_var)
            if value is not None:
                # Convert port to int if it's a number
                if config_key == "port" and value.isdigit():
                    env_config[config_key] = int(value)
                else:
                    env_config[config_key] = value

        return env_config

    def _merge_configs(
        self, toml_config: dict[str, Any], env_config: dict[str, Any]
    ) -> dict[str, Any]:
        """Merge TOML and environment configurations."""
        merged = toml_config.copy()
        merged.update(env_config)
        return merged

    def _create_adapter_config(self, config_dict: dict[str, Any]) -> AdapterConfig:
        """Create AdapterConfig from dictionary."""
        if not config_dict:
            raise ValueError("No database configuration found")

        # Extract required fields
        db_type = config_dict.get("type")
        if not db_type:
            raise ValueError("Database type is required")

        # Map source_sql_dialect to source_dialect (source_sql_dialect is the preferred name in project.toml)
        source_dialect = config_dict.get("source_dialect") or config_dict.get("source_sql_dialect")

        # Create AdapterConfig
        return AdapterConfig(
            type=db_type,
            host=config_dict.get("host"),
            port=config_dict.get("port"),
            database=config_dict.get("database"),
            user=config_dict.get("user"),
            password=config_dict.get("password"),
            path=config_dict.get("path"),
            source_dialect=source_dialect,
            target_dialect=config_dict.get("target_dialect"),
            connection_timeout=config_dict.get("connection_timeout", 30),
            query_timeout=config_dict.get("query_timeout", 300),
            schema=config_dict.get("schema"),
            warehouse=config_dict.get("warehouse"),
            role=config_dict.get("role"),
            project=config_dict.get("project"),
            extra=config_dict.get("extra"),
        )


def load_database_config(
    config_name: str = "default",
    project_root: str | None = None,
    env_name: str | None = None,
) -> AdapterConfig:
    """
    Convenience function to load database configuration.

    Args:
        config_name: Name of the configuration to load
        project_root: Project root directory (defaults to current directory)
        env_name: Optional environment name to load from [environments.<name>]

    Returns:
        AdapterConfig object
    """
    manager = DatabaseConfigManager(project_root)
    return manager.load_config(config_name, env_name)
