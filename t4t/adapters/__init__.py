"""
Database adapters for the TEE execution engine.

This package provides pluggable database adapters that handle:
- Database-specific connection management
- SQL dialect conversion using SQLglot
- Database-specific optimizations and features
- Connection string validation

Each adapter is organized in its own subpackage for better maintainability.
"""

from .base import AdapterConfig, DatabaseAdapter, MaterializationType
from .bigquery import BigQueryAdapter

# Import adapters to register them
from .duckdb import DuckDBAdapter
from .postgresql import PostgreSQLAdapter
from .registry import (
    AdapterRegistry,
    get_adapter,
    is_adapter_supported,
    list_available_adapters,
    register_adapter,
)
from .snowflake import SnowflakeAdapter
from .testing import AdapterTester, benchmark_adapter, test_adapter

__all__ = [
    # Base classes and configuration
    "DatabaseAdapter",
    "AdapterConfig",
    "MaterializationType",
    # Registry and factory functions
    "AdapterRegistry",
    "get_adapter",
    "register_adapter",
    "list_available_adapters",
    "is_adapter_supported",
    # Testing utilities
    "AdapterTester",
    "test_adapter",
    "benchmark_adapter",
    # Available adapters
    "DuckDBAdapter",
    "SnowflakeAdapter",
    "PostgreSQLAdapter",
    "BigQueryAdapter",
]
