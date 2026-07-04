"""Utility methods for Snowflake operations."""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from t4t.adapters.base.core import DatabaseAdapter

logger = logging.getLogger(__name__)


class SnowflakeUtils:
    """Utility methods for Snowflake operations."""

    def __init__(self, adapter: DatabaseAdapter) -> None:
        """
        Initialize the utils.

        Args:
            adapter: SnowflakeAdapter instance
        """
        self.adapter = adapter
        self.config = adapter.config
        self.logger = adapter.logger

    def qualify_object_name(self, object_name: str) -> str:
        """Return DATABASE-prefixed name if not already fully qualified."""
        database_name = self.config.database
        if "." in object_name:
            return f"{database_name}.{object_name}"
        return f"{database_name}.{object_name}"

    def create_schema_if_needed(
        self, object_name: str, schema_metadata: dict[str, Any] | None = None
    ) -> None:
        """
        Create schema if needed for the given object name and attach tags if provided.

        Args:
            object_name: Object name (e.g., "schema.table")
            schema_metadata: Optional metadata containing tags and object_tags for the schema
        """
        if "." in object_name:
            schema_name, _ = object_name.split(".", 1)
            database_name = self.config.database
            qualified_schema_name = f"{database_name}.{schema_name}"

            if not self.adapter.connection:
                raise RuntimeError("Not connected to database. Call connect() first.")
            try:
                cursor = self.adapter.connection.cursor()
                # Check if schema exists
                cursor.execute(
                    f"SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name = '{schema_name}'"
                )
                schema_exists = cursor.fetchone()[0] > 0

                if not schema_exists:
                    cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {qualified_schema_name}")
                    self.logger.debug(f"Created schema: {qualified_schema_name}")
                else:
                    self.logger.debug(f"Schema already exists: {qualified_schema_name}")

                # Attach tags if schema was just created or if metadata is provided
                if schema_metadata and (
                    not schema_exists or schema_metadata.get("force_tag_update", False)
                ):
                    try:
                        # Add tags (dbt-style, list of strings) if present
                        tags = schema_metadata.get("tags", [])
                        if tags:
                            self.adapter.tag_manager.attach_tags(
                                "SCHEMA", qualified_schema_name, tags
                            )

                        # Add object_tags (database-style, key-value pairs) if present
                        object_tags = schema_metadata.get("object_tags", {})
                        if object_tags and isinstance(object_tags, dict):
                            self.adapter.tag_manager.attach_object_tags(
                                "SCHEMA", qualified_schema_name, object_tags
                            )
                    except Exception as e:
                        self.logger.warning(
                            f"Could not add tags to schema {qualified_schema_name}: {e}"
                        )
                        # Don't raise - schema creation succeeded, tags are optional

                cursor.close()
            except Exception as e:
                self.logger.warning(f"Could not create schema {qualified_schema_name}: {e}")

    def execute_with_cursor(self, query: str, params: tuple | None = None) -> Any:
        """Execute a query with proper cursor management."""
        if not self.adapter.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")
        cursor = self.adapter.connection.cursor()
        try:
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            result = cursor.fetchall()
            return result
        finally:
            cursor.close()

    def add_table_comment(self, table_name: str, description: str) -> None:
        """
        Add a comment to a table using Snowflake's COMMENT ON TABLE syntax.

        Args:
            table_name: Fully qualified table name (DATABASE.SCHEMA.TABLE)
            description: Description of the table
        """
        if not self.adapter.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")
        cursor = self.adapter.connection.cursor()
        try:
            # Snowflake uses COMMENT ON TABLE syntax
            comment_query = f"COMMENT ON TABLE {table_name} IS '{description.replace("'", "''")}'"
            cursor.execute(comment_query)
            self.logger.debug(f"Added comment to table {table_name}")
        except Exception as e:
            self.logger.warning(f"Could not add comment to table {table_name}: {e}")
            # Don't raise here - table creation succeeded, comments are optional
        finally:
            cursor.close()

    def add_column_comments(self, table_name: str, column_descriptions: dict[str, str]) -> None:
        """
        Add column comments to a table using Snowflake's COMMENT ON COLUMN syntax.

        Args:
            table_name: Fully qualified table name (DATABASE.SCHEMA.TABLE)
            column_descriptions: Dictionary mapping column names to descriptions
        """
        if not self.adapter.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")
        cursor = self.adapter.connection.cursor()
        try:
            for col_name, description in column_descriptions.items():
                try:
                    # Snowflake uses COMMENT ON COLUMN syntax
                    comment_query = f"COMMENT ON COLUMN {table_name}.{col_name} IS '{description.replace("'", "''")}'"
                    cursor.execute(comment_query)
                    self.logger.debug(f"Added comment to column {table_name}.{col_name}")
                except Exception as e:
                    self.logger.warning(
                        f"Could not add comment to column {table_name}.{col_name}: {e}"
                    )
                    # Continue with other columns even if one fails
        finally:
            cursor.close()
