"""
BigQuery adapter implementation.

This module provides BigQuery-specific functionality including:
- SQL dialect conversion
- BigQuery-specific optimizations
- Connection management with service account authentication
- Materialization support including external tables
"""

from .adapter import BigQueryAdapter

__all__ = ["BigQueryAdapter"]
