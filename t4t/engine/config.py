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

    def load_config(self, config_name: str = "default") -> AdapterConfig:
        """
        Load database configuration from pyproject.toml and environment variables.

        Args:
            config_name: Name of the configuration to load (default: "default")

        Returns:
            AdapterConfig object with merged configuration

        Raises:
            ValueError: If configuration is invalid or missing
        """
        # Load from pyproject.toml
        toml_config = self._load_toml_config(config_name)

        # Load from environment variables
        env_config = self._load_env_config()

        # Merge configurations (env vars override toml)
        merged_config = self._merge_configs(toml_config, env_config)

        # Validate and create AdapterConfig
        return self._create_adapter_config(merged_config)

    def _load_toml_config(self, config_name: str) -> dict[str, Any]:
        """Load configuration from pyproject.toml or project.toml."""
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
            tee_config = data.get("tool", {}).get("tee", {})

            # Start with flags if they exist
            config = {}
            if "flags" in data:
                config["extra"] = {"flags": data["flags"]}

            # Check for single database config in tool.t4t.database
            if "database" in tee_config:
                config.update(tee_config["database"])
                return config

            # Check for multiple database configs in tool.t4t.databases
            databases = tee_config.get("databases", {})
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

        # Legacy TEE_ prefix support for backward compatibility
        legacy_mappings = {
            "TEE_DB_TYPE": "type",
            "TEE_DB_HOST": "host",
            "TEE_DB_PORT": "port",
            "TEE_DB_DATABASE": "database",
            "TEE_DB_USER": "user",
            "TEE_DB_PASSWORD": "password",
            "TEE_DB_PATH": "path",
            "TEE_DB_SCHEMA": "schema",
            "TEE_DB_WAREHOUSE": "warehouse",
            "TEE_DB_ROLE": "role",
            "TEE_DB_PROJECT": "project",
            "TEE_DB_SOURCE_DIALECT": "source_dialect",
            "TEE_DB_TARGET_DIALECT": "target_dialect",
        }

        # Load T4T_ prefixed variables first (higher priority)
        for env_var, config_key in env_mappings.items():
            value = os.getenv(env_var)
            if value is not None:
                # Convert port to int if it's a number
                if config_key == "port" and value.isdigit():
                    env_config[config_key] = int(value)
                else:
                    env_config[config_key] = value

        # Load legacy TEE_ prefixed variables (lower priority - only if not already set)
        for env_var, config_key in legacy_mappings.items():
            if config_key not in env_config:  # Only set if not already defined by T4T_
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
    config_name: str = "default", project_root: str | None = None
) -> AdapterConfig:
    """
    Convenience function to load database configuration.

    Args:
        config_name: Name of the configuration to load
        project_root: Project root directory (defaults to current directory)

    Returns:
        AdapterConfig object
    """
    manager = DatabaseConfigManager(project_root)
    return manager.load_config(config_name)
