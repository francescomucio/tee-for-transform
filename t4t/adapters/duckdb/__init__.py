"""
DuckDB adapter implementation.

This module provides DuckDB-specific functionality including:
- SQL dialect conversion
- DuckDB-specific optimizations
- Connection management
- Materialization support
"""

from .adapter import DuckDBAdapter

__all__ = ["DuckDBAdapter"]
