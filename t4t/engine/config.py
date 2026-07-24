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

from t4t.adapters.base import AdapterConfig, NamingConfig
from t4t.adapters.base.config import (
    SECRET_KEYS,
    resolve_secret_ref,
)

logger = logging.getLogger(__name__)

# ── DLT-style env var convention ──────────────────────────────────────────
# ENVIRONMENTS__DEV__CONNECTION__PASSWORD -> ["environments", "dev", "connection", "password"]
# ENVIRONMENTS__DEV__CONNECTIONS__ANALYTICS__PASSWORD -> ["environments", "dev", "connections", "analytics", "password"]
#
# NOTE: The DLT parser produces UPPERCASE keys (ENVIRONMENTS, DEV, CONNECTION,
# PASSWORD) because env var names are conventionally uppercase. The merge code
# in _merge_configs lowercases them when applying to the config dict so that
# they match the lowercase keys from TOML. This is intentional — env vars are
# case-insensitive on most platforms but uppercase is the convention, while
# TOML keys are lowercase by convention.


def _parse_dlt_env_vars() -> dict[str, Any]:
    """Parse ``ENVIRONMENTS__*__*`` environment variables into a nested dict.

    Uses the dlt-style convention where double underscores represent
    nesting levels. For example::

        ENVIRONMENTS__DEV__CONNECTION__PASSWORD = "s3cret"

    becomes::

        {"ENVIRONMENTS": {"DEV": {"CONNECTION": {"PASSWORD": "s3cret"}}}}

    Returns:
        A nested dict built from matching environment variables.
    """
    result: dict[str, Any] = {}
    prefix = "ENVIRONMENTS__"
    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue
        if not value:
            continue
        parts = key.split("__")
        if len(parts) < 2:
            continue
        # Navigate/create the nested dict and set the leaf value
        parent = result
        for part in parts[:-1]:
            if part not in parent:
                parent[part] = {}
            parent = parent[part]
        parent[parts[-1]] = value
    return result


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge *override* into *base* (mutates base in place).

    For keys where both sides are dicts, recurse. Otherwise override wins.
    """
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def is_env_protected(project_folder: str | Path, env_name: str | None) -> bool:
    """Check if an environment is marked as protected in project.toml.

    Args:
        project_folder: Path to the project folder containing project.toml.
        env_name: The environment name to check. Returns False if None.

    Returns:
        True if the environment exists and has ``protected = true``.
    """
    if not env_name:
        return False
    toml_path = Path(project_folder) / "project.toml"
    if not toml_path.exists():
        return False
    try:
        with open(toml_path, "rb") as f:
            config = tomllib.load(f)
        environments = config.get("environments", {})
        env_config = environments.get(env_name, {})
        if not isinstance(env_config, dict):
            return False
        return bool(env_config.get("protected", False))
    except Exception:
        return False


def get_state_backend_name(project_folder: str | Path, env_name: str | None) -> str:
    """Read ``environments.<env>.state.backend`` from project.toml (#20).

    Returns ``"local"`` -- today's behavior, fully backward compatible --
    when: no environment is given, project.toml doesn't exist, the
    environment has no ``[environments.<env>.state]`` section, or
    ``backend`` is missing/unrecognized. Only ``"warehouse"`` selects
    ``WarehouseStateBackend``; any other value (including a typo) is
    treated as ``"local"`` with a warning, the same fail-safe-default
    pattern as ``is_env_protected`` above.

    Args:
        project_folder: Path to the project folder containing project.toml.
        env_name: The environment name to check. Returns "local" if None.

    Returns:
        ``"local"`` or ``"warehouse"``.
    """
    if not env_name:
        return "local"
    toml_path = Path(project_folder) / "project.toml"
    if not toml_path.exists():
        return "local"
    try:
        with open(toml_path, "rb") as f:
            config = tomllib.load(f)
        environments = config.get("environments", {})
        env_config = environments.get(env_name, {})
        if not isinstance(env_config, dict):
            return "local"
        state_config = env_config.get("state", {})
        if not isinstance(state_config, dict):
            return "local"
        backend = state_config.get("backend", "local")
        if backend not in ("local", "warehouse"):
            logger.warning(
                "Unrecognized state.backend %r for environment %r; using 'local'.",
                backend,
                env_name,
            )
            return "local"
        return str(backend)
    except Exception as e:
        logger.warning("Could not read state.backend from project.toml: %s", e)
        return "local"


class DatabaseConfigManager:
    """Manages database configurations from multiple sources."""

    def __init__(self, project_root: str | None = None) -> None:
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.logger = logging.getLogger(self.__class__.__name__)

    def load_config(self, config_name: str = "default") -> AdapterConfig:
        """
        Load database configuration from pyproject.toml and environment variables.

        Precedence (highest to lowest):
        1. ``ENVIRONMENTS__*__*`` env var (dlt-style, automatic)
        2. ``T4T_DB_*`` env var (legacy)
        3. ``env:`` / ``file:`` reference in TOML (explicit)
        4. Literal value in TOML

        Args:
            config_name: Name of the environment to load (default: "default").

        Returns:
            AdapterConfig object with merged configuration.

        Raises:
            ValueError: If configuration is invalid or missing.
        """
        # 1. Load from pyproject.toml
        toml_config = self._load_toml_config(config_name)

        # 2. Load from environment variables
        env_config = self._load_env_config()

        # 3. Merge configurations (env vars override toml)
        merged_config = self._merge_configs(toml_config, env_config, config_name)

        # 4. Validate and create AdapterConfig
        return self._create_adapter_config(merged_config)

    def _load_toml_config(self, config_name: str) -> dict[str, Any]:
        """Load configuration from pyproject.toml or project.toml.

        Loads ``[environments.default]`` first, then merges
        ``[environments.<config_name>]`` on top. Extracts ``connection``
        as the default engine and ``connections.*`` as additional engines.

        Prefers ``project.toml`` over ``pyproject.toml`` when both exist,
        because ``pyproject.toml`` may belong to a parent Python project
        and contain no t4t configuration.
        """
        # Try project.toml first (t4t-specific config file)
        toml_file = self.project_root / "project.toml"
        if not toml_file.exists():
            # Fall back to pyproject.toml
            toml_file = self.project_root / "pyproject.toml"
            if not toml_file.exists():
                self.logger.debug("No project.toml or pyproject.toml found")
                return {}

        try:
            with open(toml_file, "rb") as f:
                data = tomllib.load(f)

            # Look for [tool.t4t.database], [tool.t4t.databases], or [environments.*]
            t4t_config = data.get("tool", {}).get("t4t", {})

            # Start with flags if they exist
            config: dict[str, Any] = {}
            if "flags" in data:
                config["extra"] = {"flags": data["flags"]}

            # ── Load base config from tool.t4t.database or tool.t4t.databases ──
            base_config: dict[str, Any] = {}

            if "database" in t4t_config:
                base_config.update(t4t_config["database"])
            else:
                databases = t4t_config.get("databases", {})
                if isinstance(databases, dict) and config_name in databases:
                    base_config.update(databases[config_name])

            # ── Load environments ──────────────────────────────────────────────
            environments = data.get("environments", {})
            if not isinstance(environments, dict):
                environments = {}

            # Start with [environments.default] if it exists
            env_config: dict[str, Any] = {}
            default_env = environments.get("default")
            if isinstance(default_env, dict):
                self.logger.debug("Loading [environments.default] config")
                env_config = self._extract_env_config(default_env)

            # Merge specific environment on top
            specific_env = environments.get(config_name)
            if isinstance(specific_env, dict):
                self.logger.debug(
                    "Loading [environments.%s] config (merging on top of default)",
                    config_name,
                )
                specific_config = self._extract_env_config(specific_env)
                _deep_merge(env_config, specific_config)

            # Merge base_config + env_config (env_config overrides base)
            config.update(base_config)
            config.update(env_config)

            # If we have any config, return it
            if config.get("type") or config.get("connection"):
                return config

            # No environments found — error (legacy [connection] removed)
            if not environments:
                self.logger.debug("No [environments.*] sections found in TOML file")
                return {}

            self.logger.debug(
                "Environment '%s' not found in [environments.*] sections",
                config_name,
            )
            return {}

        except Exception as e:
            self.logger.warning("Could not read pyproject.toml: %s", e)
            return {}

    def _extract_env_config(self, env_section: dict[str, Any]) -> dict[str, Any]:
        """Extract connection and connections config from an environment section.

        Args:
            env_section: The dict for a single environment (e.g. ``environments.dev``).

        Returns:
            A flat config dict with ``connection`` fields merged in, plus
            ``_naming_config`` and ``_connections`` keys for multi-engine.
        """
        result: dict[str, Any] = {}

        # Extract naming config
        naming_raw = env_section.get("naming")
        if isinstance(naming_raw, dict):
            naming = NamingConfig(
                schema_prefix=naming_raw.get("schema_prefix"),
                schema_suffix=naming_raw.get("schema_suffix"),
                database=naming_raw.get("database"),
            )
            result["_naming_config"] = naming

        # Extract default connection (flattened into top-level keys)
        connection = env_section.get("connection")
        if isinstance(connection, dict):
            for key, value in connection.items():
                result[key] = value

        # Extract additional named connections (multi-engine)
        connections = env_section.get("connections")
        if isinstance(connections, dict):
            result["_connections"] = {}
            for conn_name, conn_config in connections.items():
                if isinstance(conn_config, dict):
                    result["_connections"][conn_name] = dict(conn_config)

        return result

    def _load_env_config(self) -> dict[str, Any]:
        """Load configuration from environment variables.

        Supports:
        - ``ENVIRONMENTS__*__*`` dlt-style convention (highest precedence)
        - ``T4T_DB_*`` legacy env vars (backward compat)
        """
        env_config: dict[str, Any] = {}

        # 1. DLT-style ENVIRONMENTS__*__* env vars
        dlt_config = _parse_dlt_env_vars()
        if dlt_config:
            env_config["_dlt_env_config"] = dlt_config

        # 2. Legacy T4T_DB_* env vars
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

        for env_var, config_key in env_mappings.items():
            value = os.getenv(env_var)
            if value is not None:
                if config_key == "port" and value.isdigit():
                    env_config[config_key] = int(value)
                else:
                    env_config[config_key] = value

        return env_config

    def _merge_configs(
        self,
        toml_config: dict[str, Any],
        env_config: dict[str, Any],
        config_name: str = "default",
    ) -> dict[str, Any]:
        """Merge TOML and environment configurations.

        1. Start with TOML config
        2. Apply legacy ``T4T_DB_*`` env vars on top
        3. Apply dlt-style ``ENVIRONMENTS__*__*`` env vars for the requested env on top
        4. Resolve secret references (``env:``, ``file:``)
        5. Warn on literal secrets in non-dev environments
        """
        merged = toml_config.copy()

        # Apply legacy T4T_DB_* env vars (step 2)
        for key in (
            "type",
            "host",
            "port",
            "database",
            "user",
            "password",
            "path",
            "schema",
            "warehouse",
            "role",
            "project",
            "source_dialect",
            "target_dialect",
        ):
            if key in env_config:
                merged[key] = env_config[key]

        # Apply dlt-style ENVIRONMENTS__*__* env vars (step 3) — only for requested env
        dlt_config = env_config.get("_dlt_env_config")
        if dlt_config:
            envs = dlt_config.get("ENVIRONMENTS", {})
            # Look up the requested environment (case-insensitive match on env name)
            env_data = None
            for env_name, data in envs.items():
                if env_name.upper() == config_name.upper():
                    env_data = data
                    break
            if env_data is None and config_name.lower() == "default" and "DEFAULT" in envs:
                env_data = envs["DEFAULT"]
            if isinstance(env_data, dict):
                connection = env_data.get("CONNECTION")
                if isinstance(connection, dict):
                    for k, v in connection.items():
                        merged[k.lower()] = v
                connections = env_data.get("CONNECTIONS")
                if isinstance(connections, dict):
                    if "_connections" not in merged:
                        merged["_connections"] = {}
                    for conn_name, conn_config in connections.items():
                        if isinstance(conn_config, dict):
                            # Lowercase the keys for consistency with TOML config
                            normalized = {k.lower(): v for k, v in conn_config.items()}
                            existing = merged["_connections"].get(conn_name.lower())
                            if isinstance(existing, dict):
                                existing.update(normalized)
                            else:
                                merged["_connections"][conn_name.lower()] = normalized

        # Resolve secret references (step 4)
        for key in list(merged.keys()):
            if key in SECRET_KEYS and isinstance(merged[key], str):
                original = merged[key]
                resolved = resolve_secret_ref(original)
                if resolved != original:
                    self.logger.debug("Resolved secret reference for '%s'", key)
                    merged[key] = resolved

        # Resolve secrets in additional connections
        raw_connections = merged.get("_connections")
        if isinstance(raw_connections, dict):
            for conn_name, conn_dict in raw_connections.items():
                if isinstance(conn_dict, dict):
                    for key in list(conn_dict.keys()):
                        if key in SECRET_KEYS and isinstance(conn_dict[key], str):
                            original = conn_dict[key]
                            resolved = resolve_secret_ref(original)
                            if resolved != original:
                                self.logger.debug(
                                    "Resolved secret reference for '%s.%s'", conn_name, key
                                )
                                conn_dict[key] = resolved

        # Warn on literal secrets in non-dev environments (step 5)
        # We can't know the env name here, so we do a simple heuristic:
        # if password looks like a literal (not a ref), log a debug message
        if "password" in merged and isinstance(merged["password"], str):
            pw = merged["password"]
            if not pw.startswith("env:") and not pw.startswith("file:"):
                self.logger.warning(
                    "Literal password value found in config — "
                    "consider using 'env:VAR_NAME' or 'file:/path' for security"
                )

        return merged

    def _create_adapter_config(self, config_dict: dict[str, Any]) -> AdapterConfig:
        """Create AdapterConfig from dictionary."""
        if not config_dict:
            raise ValueError("No database configuration found")

        # Extract required fields
        db_type = config_dict.get("type")
        if not db_type:
            raise ValueError("Database type is required")

        # Map source_sql_dialect to source_dialect
        source_dialect = config_dict.get("source_dialect") or config_dict.get("source_sql_dialect")

        # Build additional connections (multi-engine)
        connections: dict[str, AdapterConfig] | None = None
        raw_connections = config_dict.get("_connections")
        if isinstance(raw_connections, dict):
            connections = {}
            for conn_name, conn_dict in raw_connections.items():
                if isinstance(conn_dict, dict):
                    conn_type = conn_dict.get("type")
                    if conn_type:
                        conn_source_dialect = conn_dict.get("source_dialect") or conn_dict.get(
                            "source_sql_dialect"
                        )
                        connections[conn_name] = AdapterConfig(
                            type=conn_type,
                            host=conn_dict.get("host"),
                            port=conn_dict.get("port"),
                            database=conn_dict.get("database"),
                            user=conn_dict.get("user"),
                            password=conn_dict.get("password"),
                            path=conn_dict.get("path"),
                            source_dialect=conn_source_dialect,
                            target_dialect=conn_dict.get("target_dialect"),
                            connection_timeout=conn_dict.get("connection_timeout", 30),
                            query_timeout=conn_dict.get("query_timeout", 300),
                            schema=conn_dict.get("schema"),
                            warehouse=conn_dict.get("warehouse"),
                            role=conn_dict.get("role"),
                            project=conn_dict.get("project"),
                            extra=conn_dict.get("extra"),
                        )

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
            naming=config_dict.get("_naming_config"),
            connections=connections,
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
