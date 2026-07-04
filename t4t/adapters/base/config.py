"""
Configuration types and structures for database adapters.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class MaterializationType(Enum):
    """Supported materialization types across databases."""

    TABLE = "table"
    VIEW = "view"
    MATERIALIZED_VIEW = "materialized_view"
    EXTERNAL_TABLE = "external_table"
    INCREMENTAL = "incremental"


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

    # Additional custom settings
    extra: dict[str, Any] | None = None
