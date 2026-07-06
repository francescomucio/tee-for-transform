"""
Configuration types and structures for database adapters.
"""

import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class MaterializationType(Enum):
    """Supported materialization types across databases."""

    TABLE = "table"
    VIEW = "view"
    MATERIALIZED_VIEW = "materialized_view"
    EXTERNAL_TABLE = "external_table"
    INCREMENTAL = "incremental"


@dataclass
class NamingConfig:
    """Naming strategy configuration for environment-aware object naming.

    Controls how database objects (tables, views, functions) are named
    per environment. The v1 strategy uses ``schema_prefix`` to prefix
    the schema portion of qualified names (e.g. ``dev_my_schema.my_table``).
    """

    schema_prefix: str | None = None
    """Prefix prepended to the schema name (v1 strategy).

    Example: ``"dev_"`` turns ``my_schema.my_table`` into
    ``dev_my_schema.my_table``.
    """

    schema_suffix: str | None = None
    """Suffix appended to the schema name (reserved for future use)."""

    database: str | None = None
    """Override database name (reserved for future use)."""


# ── Secret Provider Protocol ──────────────────────────────────────────────


@runtime_checkable
class SecretProvider(Protocol):
    """Protocol for resolving secret references in configuration values.

    A secret reference is a string like ``"env:MY_PASSWORD"`` or
    ``"file:/run/secrets/pw"``. The prefix identifies which provider
    should handle the reference.
    """

    prefix: str
    """The prefix that identifies this provider (e.g. ``"env:"``, ``"file:"``)."""

    def resolve(self, ref: str) -> str:
        """Resolve a secret reference to its actual value.

        Args:
            ref: The full reference string including the prefix
                 (e.g. ``"env:MY_PASSWORD"``).

        Returns:
            The resolved secret value.

        Raises:
            ValueError: If the reference cannot be resolved.
        """
        ...


class EnvSecretProvider:
    """Resolves ``"env:<VAR_NAME>"`` references from environment variables."""

    prefix = "env:"

    def resolve(self, ref: str) -> str:
        """Read the value from the environment variable named after the prefix.

        Args:
            ref: ``"env:MY_VAR"`` — the part after ``"env:"`` is the env var name.

        Returns:
            The value of the environment variable.

        Raises:
            ValueError: If the environment variable is not set or empty.
        """
        var_name = ref[len(self.prefix) :]
        value = os.environ.get(var_name)
        if value is None:
            raise ValueError(
                f"Environment variable '{var_name}' is not set (referenced by '{ref}')"
            )
        return value


class FileSecretProvider:
    """Resolves ``"file:<path>"`` references by reading the file contents."""

    prefix = "file:"

    def resolve(self, ref: str) -> str:
        """Read the first line from the file at the given path.

        Args:
            ref: ``"file:/run/secrets/pw"`` — the part after ``"file:"`` is the
                 file path.

        Returns:
            The contents of the file (stripped of trailing whitespace).

        Raises:
            FileNotFoundError: If the file does not exist.
            PermissionError: If the file cannot be read.
        """
        path = ref[len(self.prefix) :]
        with open(path) as f:
            return f.read().strip()


# Built-in registry of secret providers
_BUILTIN_SECRET_PROVIDERS: list[SecretProvider] = [
    EnvSecretProvider(),
    FileSecretProvider(),
]

# Keys whose values may contain secret references (env:/file:).
# Shared between config loading and CLI utils so they stay in sync.
SECRET_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "user",
        "host",
        "database",
        "path",
        "warehouse",
        "role",
        "project",
    }
)


def resolve_secret_ref(value: str, providers: list[SecretProvider] | None = None) -> str:
    """Resolve a secret reference string using registered providers.

    If *value* does not start with any known provider prefix, it is
    returned unchanged (literal value).

    Args:
        value: The configuration value to check for secret references.
        providers: Optional list of providers. Defaults to built-in providers.

    Returns:
        The resolved value, or the original value if no provider matches.
    """
    if providers is None:
        providers = _BUILTIN_SECRET_PROVIDERS
    for provider in providers:
        if value.startswith(provider.prefix):
            return provider.resolve(value)
    return value


# ── AdapterConfig ─────────────────────────────────────────────────────────


@dataclass
class AdapterConfig:
    """Configuration for database adapters."""

    # Database connection
    type: str
    host: str | None = None
    port: int | None = None
    database: str | None = None
    user: str | None = None
    password: str | None = None
    path: str | None = None  # For file-based databases like DuckDB

    # SQL dialect settings
    source_dialect: str | None = None  # Dialect to convert FROM
    target_dialect: str | None = None  # Dialect to convert TO (usually auto-detected)

    # Connection settings
    connection_timeout: int = 30
    query_timeout: int = 300

    # Database-specific settings
    schema: str | None = None
    warehouse: str | None = None  # For Snowflake
    role: str | None = None  # For Snowflake
    project: str | None = None  # For BigQuery

    # Naming strategy (env-aware)
    naming: NamingConfig | None = None

    # Multi-engine: additional named connections
    connections: dict[str, AdapterConfig] | None = None
    """Additional named engine configurations for multi-engine support.

    The primary connection is stored in the top-level fields (``type``,
    ``host``, etc.). Additional named engines are stored here, keyed by
    name (e.g. ``"analytics"``, ``"reporting"``).
    """

    # Additional custom settings
    extra: dict[str, Any] | None = None
