"""
Enhanced execution engine with pluggable database adapters.

This module provides the main execution engine that supports:
- Pluggable database adapters
- Automatic SQL dialect conversion using SQLglot
- Configuration management from pyproject.toml and environment variables
- Database-specific optimizations and features
"""

from t4t.adapters import AdapterConfig, AdapterRegistry, get_adapter

from .config import DatabaseConfigManager, load_database_config
from .execution_engine import ExecutionEngine
from .executor import ModelExecutor

__all__ = [
    # Main system
    "ExecutionEngine",
    "ModelExecutor",
    "load_database_config",
    "DatabaseConfigManager",
    "get_adapter",
    "AdapterConfig",
    "AdapterRegistry",
]
