"""View creation and management for Snowflake."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from t4t.adapters.base.core import DatabaseAdapter

logger = logging.getLogger(__name__)


class ViewHandler:
    """Handles view creation with column comments for Snowflake."""

    def __init__(self, adapter: DatabaseAdapter) -> None:
        """
        Initialize the view handler.

        Args:
            adapter: SnowflakeAdapter instance
        """
        self.adapter = adapter
        self.config = adapter.config
        self.logger = adapter.logger
        self.tag_manager = adapter.tag_manager

    def create(self, view_name: str, query: str, metadata: dict[str, Any] | None = None) -> None:
        """Create a view from a qualified SQL query."""
        if not self.adapter.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        # Create schema if needed
        self.adapter.utils.create_schema_if_needed(view_name)

        # Use 3-part naming for the view (DATABASE.SCHEMA.VIEW)
        qualified_view_name = self.adapter.utils.qualify_object_name(view_name)

        # Build the CREATE VIEW statement with inline comments if metadata is provided
        if metadata and (
            ("schema" in metadata and metadata["schema"])
            or ("description" in metadata and metadata["description"])
        ):
            create_query = self._build_view_with_column_comments(
                qualified_view_name, query, metadata
            )
        else:
            create_query = f"CREATE OR REPLACE VIEW {qualified_view_name} AS {query}"

        # Log the SQL being executed at DEBUG level
        self.logger.debug(f"Executing SQL for view {view_name}:")
        self.logger.debug(f"  Original query: {query}")
        self.logger.debug(f"  Full CREATE statement: {create_query}")

        try:
            cursor = self.adapter.connection.cursor()
            cursor.execute(create_query)
            cursor.close()
            self.logger.info(f"Created view: {view_name}")

            # Add tags if metadata is provided
            if metadata:
                # Add tags (dbt-style, list of strings) if present
                tags = metadata.get("tags", [])
                if tags:
                    try:
                        self.tag_manager.attach_tags("VIEW", qualified_view_name, tags)
                    except Exception as e:
                        self.logger.warning(f"Could not add tags for view {view_name}: {e}")
                        # Don't raise here - view creation succeeded, tags are optional

                # Add object_tags (database-style, key-value pairs) if present
                object_tags = metadata.get("object_tags", {})
                if object_tags and isinstance(object_tags, dict):
                    try:
                        self.tag_manager.attach_object_tags(
                            "VIEW", qualified_view_name, object_tags
                        )
                    except Exception as e:
                        self.logger.warning(f"Could not add object_tags for view {view_name}: {e}")
                        # Don't raise here - view creation succeeded, tags are optional

            # Note: View and column comments are now included inline during creation

        except Exception as e:
            self.logger.error(f"Failed to create view {view_name}: {e}")
            raise

    def _build_view_with_column_comments(
        self, qualified_view_name: str, query: str, metadata: dict[str, Any]
    ) -> str:
        """
        Build a CREATE VIEW statement with inline column comments and view comment for Snowflake.

        Snowflake supports both view comments and column comments inline during view creation:
        CREATE OR REPLACE VIEW schema.view_name COMMENT='view comment' (
            column1 COMMENT 'comment1',
            column2 COMMENT 'comment2'
        ) AS SELECT ...

        Args:
            qualified_view_name: Fully qualified view name (DATABASE.SCHEMA.VIEW)
            query: The SELECT query for the view
            metadata: Metadata containing schema information

        Returns:
            Complete CREATE VIEW statement with inline column comments and view comment
        """
        try:
            # Extract view description from metadata
            view_description = metadata.get("description", "")
            escaped_view_description = (
                view_description.replace("'", "''") if view_description else ""
            )

            # Extract column descriptions from metadata
            column_descriptions = self.adapter._validate_column_metadata(metadata)

            if not column_descriptions and not escaped_view_description:
                # No descriptions available, use simple CREATE VIEW
                return f"CREATE OR REPLACE VIEW {qualified_view_name} AS {query}"

            # Build the view comment part
            view_comment_part = (
                f" COMMENT='{escaped_view_description}'" if escaped_view_description else ""
            )

            if not column_descriptions:
                # Only view comment, no column comments
                create_query = (
                    f"CREATE OR REPLACE VIEW {qualified_view_name}{view_comment_part} AS {query}"
                )
            else:
                # Both view comment and column comments
                column_list = []
                for col_name, description in column_descriptions.items():
                    # Escape single quotes in description
                    escaped_description = description.replace("'", "''")
                    column_list.append(f"{col_name} COMMENT '{escaped_description}'")

                # Create the view with both view comment and inline column comments
                column_spec = ",\n    ".join(column_list)
                create_query = f"""CREATE OR REPLACE VIEW {qualified_view_name}{view_comment_part} (
    {column_spec}
) AS {query}"""

            self.logger.debug(f"Built view with inline comments: {create_query}")
            return create_query

        except Exception as e:
            self.logger.warning(f"Failed to build view with comments: {e}")
            # Fall back to simple CREATE VIEW without comments
            return f"CREATE OR REPLACE VIEW {qualified_view_name} AS {query}"
