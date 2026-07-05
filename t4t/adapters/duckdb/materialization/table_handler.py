"""Table creation and management for DuckDB."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from t4t.adapters.base.core import DatabaseAdapter

logger = logging.getLogger(__name__)


class TableHandler:
    """Handles table creation and management for DuckDB."""

    def __init__(self, adapter: DatabaseAdapter) -> None:
        """
        Initialize the table handler.

        Args:
            adapter: DuckDBAdapter instance
        """
        self.adapter = adapter
        self.config = adapter.config
        self.logger = adapter.logger

    def create(self, table_name: str, query: str, metadata: dict[str, Any] | None = None) -> None:
        """Create a table from a qualified SQL query with optional column metadata."""
        if not self.adapter.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        # Create schema if needed
        self.adapter.utils.create_schema_if_needed(table_name)

        # Convert SQL and qualify table references
        converted_query = self.adapter.utils.convert_and_qualify_sql(query)

        # Wrap the query in a CREATE TABLE statement
        create_query = f"CREATE OR REPLACE TABLE {table_name} AS {converted_query}"

        try:
            self.adapter.utils.execute_query(create_query)
            self.logger.debug(f"Created table: {table_name}")

            # Add table and column comments if metadata is provided
            if metadata:
                try:
                    # Add table comment if description is provided
                    table_description = metadata.get("description")
                    if table_description:
                        self.adapter.utils.add_table_comment(table_name, table_description)

                    # Add column comments
                    column_descriptions = self.adapter._validate_column_metadata(metadata)
                    if column_descriptions:
                        self.adapter.utils.add_column_comments(table_name, column_descriptions)
                except ValueError as e:
                    self.logger.error(f"Invalid metadata for table {table_name}: {e}")
                    raise
                except Exception as e:
                    self.logger.warning(f"Could not add comments for table {table_name}: {e}")
                    # Don't raise here - table creation succeeded, comments are optional

        except Exception as e:
            self.logger.error(f"Failed to create table {table_name}: {e}")
            raise
