"""Utility methods for DuckDB operations."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from t4t.adapters.base.core import DatabaseAdapter

logger = logging.getLogger(__name__)


class DuckDBUtils:
    """Utility methods for DuckDB operations."""

    def __init__(self, adapter: DatabaseAdapter) -> None:
        """
        Initialize the utils.

        Args:
            adapter: DuckDBAdapter instance
        """
        self.adapter = adapter
        self.config = adapter.config
        self.logger = adapter.logger

    def create_schema_if_needed(self, object_name: str) -> None:
        """Create schema if needed for the given object name."""
        if "." in object_name:
            schema_name, _ = object_name.split(".", 1)
            try:
                self.adapter.connection.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_name}")
                self.logger.debug(f"Created schema: {schema_name}")
            except Exception as e:
                self.logger.warning(f"Could not create schema {schema_name}: {e}")

    def convert_and_qualify_sql(self, query: str) -> str:
        """Convert SQL dialect and qualify table references if schema is specified."""
        converted_query = self.adapter.convert_sql_dialect(query)
        if self.config.schema:
            converted_query = self.adapter.qualify_table_references(
                converted_query, self.config.schema
            )
        return converted_query

    def execute_query(self, query: str) -> None:
        """Execute a simple query with error handling."""
        if not self.adapter.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")
        try:
            self.adapter.connection.execute(query)
        except Exception as e:
            self.logger.error(f"Error executing query: {e}")
            raise

    def add_table_comment(self, table_name: str, description: str) -> None:
        """
        Add a comment to a table using DuckDB's COMMENT ON TABLE syntax.

        Args:
            table_name: Name of the table
            description: Description of the table
        """
        if not self.adapter.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")
        try:
            # DuckDB uses COMMENT ON TABLE syntax (PostgreSQL-compatible)
            comment_query = f"COMMENT ON TABLE {table_name} IS '{description.replace("'", "''")}'"
            self.adapter.connection.execute(comment_query)
            self.logger.debug(f"Added comment to table {table_name}")
        except Exception as e:
            self.logger.warning(f"Could not add comment to table {table_name}: {e}")
            # Don't raise here - table creation succeeded, comments are optional

    def add_column_comments(self, table_name: str, column_descriptions: dict[str, str]) -> None:
        """
        Add column comments to a table using DuckDB's COMMENT ON COLUMN syntax.

        Args:
            table_name: Name of the table
            column_descriptions: Dictionary mapping column names to descriptions
        """
        if not self.adapter.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")
        for col_name, description in column_descriptions.items():
            try:
                # DuckDB uses COMMENT ON COLUMN syntax (PostgreSQL-compatible)
                comment_query = f"COMMENT ON COLUMN {table_name}.{col_name} IS '{description.replace("'", "''")}'"
                self.adapter.connection.execute(comment_query)
                self.logger.debug(f"Added comment to column {table_name}.{col_name}")
            except Exception as e:
                self.logger.warning(f"Could not add comment to column {table_name}.{col_name}: {e}")
                # Continue with other columns even if one fails
