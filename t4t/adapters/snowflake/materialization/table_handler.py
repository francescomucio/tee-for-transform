"""Table creation and management for Snowflake."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from t4t.adapters.base.core import DatabaseAdapter

logger = logging.getLogger(__name__)


class TableHandler:
    """Handles table creation and management for Snowflake."""

    def __init__(self, adapter: DatabaseAdapter) -> None:
        """
        Initialize the table handler.

        Args:
            adapter: SnowflakeAdapter instance
        """
        self.adapter = adapter
        self.config = adapter.config
        self.logger = adapter.logger
        self.tag_manager = adapter.tag_manager

    def create(self, table_name: str, query: str, metadata: dict[str, Any] | None = None) -> None:
        """Create a table from a qualified SQL query with optional column metadata."""
        if not self.adapter.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        # Create schema if needed (schema tags will be handled by execution engine)
        self.adapter.utils.create_schema_if_needed(table_name)

        # Use 3-part naming for the table (DATABASE.SCHEMA.TABLE)
        qualified_table_name = self.adapter.utils.qualify_object_name(table_name)
        create_query = f"CREATE OR REPLACE TABLE {qualified_table_name} AS {query}"

        # Log the SQL being executed at DEBUG level
        self.logger.debug(f"Executing SQL for table {table_name}:")
        self.logger.debug(f"  Original query: {query}")
        self.logger.debug(f"  Full CREATE statement: {create_query}")

        try:
            cursor = self.adapter.connection.cursor()
            cursor.execute(create_query)
            cursor.close()
            self.logger.info(f"Created table: {table_name}")

            # Add table and column comments if metadata is provided
            if metadata:
                try:
                    # Add table comment if description is provided
                    table_description = metadata.get("description")
                    if table_description:
                        self.adapter.utils.add_table_comment(
                            qualified_table_name, table_description
                        )

                    # Add column comments
                    column_descriptions = self.adapter._validate_column_metadata(metadata)
                    if column_descriptions:
                        self.adapter.utils.add_column_comments(
                            qualified_table_name, column_descriptions
                        )

                    # Add tags (dbt-style, list of strings) if present
                    tags = metadata.get("tags", [])
                    if tags:
                        self.tag_manager.attach_tags("TABLE", qualified_table_name, tags)

                    # Add object_tags (database-style, key-value pairs) if present
                    object_tags = metadata.get("object_tags", {})
                    if object_tags and isinstance(object_tags, dict):
                        self.tag_manager.attach_object_tags(
                            "TABLE", qualified_table_name, object_tags
                        )
                except ValueError as e:
                    self.logger.error(f"Invalid metadata for table {table_name}: {e}")
                    raise
                except Exception as e:
                    self.logger.warning(f"Could not add comments/tags for table {table_name}: {e}")
                    # Don't raise here - table creation succeeded, comments/tags are optional

        except Exception as e:
            self.logger.error(f"Failed to create table {table_name}: {e}")
            raise
