"""View creation and management for DuckDB."""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from t4t.adapters.base.core import DatabaseAdapter

logger = logging.getLogger(__name__)


class ViewHandler:
    """Handles view creation for DuckDB."""

    def __init__(self, adapter: DatabaseAdapter) -> None:
        """
        Initialize the view handler.

        Args:
            adapter: DuckDBAdapter instance
        """
        self.adapter = adapter
        self.config = adapter.config
        self.logger = adapter.logger

    def create(self, view_name: str, query: str, metadata: dict[str, Any] | None = None) -> None:
        """Create a view from a qualified SQL query."""
        if not self.adapter.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        # Create schema if needed
        self.adapter.utils.create_schema_if_needed(view_name)

        # Convert SQL and qualify table references
        converted_query = self.adapter.utils.convert_and_qualify_sql(query)

        # Wrap the query in a CREATE VIEW statement
        create_query = f"CREATE OR REPLACE VIEW {view_name} AS {converted_query}"

        try:
            self.adapter.utils.execute_query(create_query)
            self.logger.info(f"Created view: {view_name}")

            # Add view and column comments if metadata is provided
            if metadata:
                # Add view description
                if "description" in metadata and metadata["description"]:
                    self.adapter.utils.add_table_comment(view_name, metadata["description"])

                # Add column comments
                if "schema" in metadata and metadata["schema"]:
                    column_descriptions = self.adapter._validate_column_metadata(metadata)
                    if column_descriptions:
                        self.adapter.utils.add_column_comments(view_name, column_descriptions)

        except Exception as e:
            self.logger.error(f"Failed to create view {view_name}: {e}")
            raise
