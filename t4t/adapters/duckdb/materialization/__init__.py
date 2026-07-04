"""Materialization components for DuckDB."""

from .incremental_handler import IncrementalHandler
from .table_handler import TableHandler
from .view_handler import ViewHandler

__all__ = ["TableHandler", "ViewHandler", "IncrementalHandler"]
