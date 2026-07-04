"""
PostgreSQL adapter implementation.

This module provides PostgreSQL-specific functionality including:
- SQL dialect conversion
- PostgreSQL-specific optimizations
- Connection management
- Materialization support
"""

from .adapter import PostgreSQLAdapter

__all__ = ["PostgreSQLAdapter"]
