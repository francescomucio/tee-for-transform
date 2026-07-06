"""Database configuration management.

This module handles loading database configurations from pyproject.toml
and environment variables with proper precedence and validation.
"""

import logging
import os
import re
import tomllib
from pathlib import Path
from typing import Any

from t4t.adapters.base import AdapterConfig

# Keys that are considered secret-bearing and should be redacted in logs
_SECRET_KEYS = frozenset(
    {
        "password",
        "token",
        "secret",
        "api_key",
        "private_key",
        "access_key",
        "client_secret",
    }
)

# Reference prefix scheme — extensible to future managers (vault:, aws-sm:, ...)
_REF_PREFIXES = frozenset({"env:", "file:"})

# Regex for a valid reference prefix word (letters, digits, hyphens, underscores)
_REF_PREFIX_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_-]*$")


def _looks_like_reference(value: str) -> bool:
    """Check if a string value looks like a known reference (prefix:rest).

    A value looks like a reference if its prefix is one of the known
    prefixes in ``_REF_PREFIXES``.  This avoids false positives such as
    ``localhost:5432`` or ``C:/path``.
    """
    if ":" not in value:
        return False
    prefix, _, _ = value.partition(":")
    return f"{prefix}:" in _REF_PREFIXES


def _looks_like_any_reference(value: str) -> bool:
    """Check if a string matches the general ``word:rest`` reference pattern.

    Unlike ``_looks_like_reference``, this does not require the prefix to
    be known — it catches unknown prefixes such as ``vault:`` or ``aws-sm:``
    so we can raise a clear error.
    """
    if ":" not in value:
        return False
    prefix, _, _ = value.partition(":")
    return bool(prefix) and bool(_REF_PREFIX_RE.match(prefix))


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
            t4t_config = data.get("tool", {}).get("t4t", {})

            # Start with flags if they exist
            config = {}
            if "flags" in data:
                config["extra"] = {"flags": data["flags"]}

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
        # Warn about literal secrets in the merged config (before resolution,
        # so env: references are still detected as non-literal and env var
        # overrides suppress warnings for overridden TOML values).
        self._warn_literal_secrets(merged)
        # Resolve secret references after env var merge, so T4T_DB_* overrides
        # still work and don't need the reference syntax themselves.
        merged = self._resolve_secret_refs(merged)
        return merged

    def _resolve_secret_refs(self, config: dict[str, Any]) -> dict[str, Any]:
        """Resolve env: and file: secret references in config values.

        Args:
            config: Configuration dictionary with possible reference values.

        Returns:
            New dictionary with all references resolved to their actual values.
            Literal (non-reference) values pass through unchanged.

        Raises:
            ValueError: If a reference prefix is unknown or a referenced
                environment variable / file cannot be read.
        """
        resolved = {}
        for key, value in config.items():
            if not isinstance(value, str):
                resolved[key] = value
                continue

            if value.startswith("env:"):
                var_name = value[len("env:") :]
                if not var_name:
                    raise ValueError(f"Empty env: reference for key '{key}'")
                env_val = os.getenv(var_name)
                if env_val is None:
                    raise ValueError(
                        f"Environment variable '{var_name}' referenced in config key "
                        f"'{key}' is not set"
                    )
                resolved[key] = env_val

            elif value.startswith("file:"):
                file_path = value[len("file:") :]
                if not file_path:
                    raise ValueError(f"Empty file: reference for key '{key}'")
                # Resolve relative paths against project_root
                p = Path(file_path)
                if not p.is_absolute():
                    p = self.project_root / p
                try:
                    file_val = p.read_text(encoding="utf-8").rstrip("\n")
                except FileNotFoundError:
                    raise ValueError(
                        f"Secret file '{file_path}' referenced in config key '{key}' not found"
                    ) from None
                except PermissionError:
                    raise ValueError(
                        f"Permission denied reading secret file '{file_path}' "
                        f"referenced in config key '{key}'"
                    ) from None
                except OSError as e:
                    raise ValueError(
                        f"Error reading secret file '{file_path}' referenced in "
                        f"config key '{key}': {e}"
                    ) from None
                resolved[key] = file_val

            elif _looks_like_any_reference(value):
                # Value looks like a reference (e.g. "vault:my-secret") but
                # uses an unsupported prefix.
                prefix = value.split(":", 1)[0] + ":"
                raise ValueError(
                    f"Unknown reference prefix '{prefix}' for key '{key}'. "
                    f"Supported prefixes: {', '.join(sorted(_REF_PREFIXES))}"
                )

            else:
                resolved[key] = value

        return resolved

    def _redact_secrets(self, config: dict[str, Any]) -> dict[str, Any]:
        """Return a copy of *config* with secret values replaced by ``'****'``.

        This is safe for logging and error messages — it never leaks resolved
        secret values.
        """
        return {key: ("****" if key in _SECRET_KEYS else value) for key, value in config.items()}

    def _warn_literal_secrets(self, config: dict[str, Any]) -> None:
        """Emit a lint-style warning when a secret key holds a literal value.

        Literal secrets in committed config files are a security risk. Users
        should use ``env:`` or ``file:`` references instead.
        """
        for key in _SECRET_KEYS:
            value = config.get(key)
            if value is not None and isinstance(value, str) and not _looks_like_reference(value):
                self.logger.warning(
                    "Literal %s found in config — consider using env: or file: "
                    "reference instead for security",
                    key,
                )

    def _create_adapter_config(self, config_dict: dict[str, Any]) -> AdapterConfig:
        """Create AdapterConfig from dictionary."""
        if not config_dict:
            raise ValueError("No database configuration found")

        # Log the config with secrets redacted
        self.logger.debug("Creating adapter config: %s", self._redact_secrets(config_dict))

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
