"""
Snowflake adapter implementation.

This module provides Snowflake-specific functionality including:
- SQL dialect conversion from other dialects to Snowflake
- Snowflake-specific optimizations and features
- Connection management with warehouse and role support
- Materialization support including external tables
"""

from .adapter import SnowflakeAdapter

__all__ = ["SnowflakeAdapter"]
