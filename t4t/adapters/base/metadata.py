"""
Metadata handling methods for database adapters.

These methods are mixed into DatabaseAdapter via multiple inheritance.
"""

from typing import Any


class MetadataHandler:
    """Mixin class for handling table and column metadata."""

    def _validate_column_metadata(self, metadata: dict[str, Any] | None) -> dict[str, str]:
        """
        Validate and extract column descriptions from metadata.

        Args:
            metadata: Model metadata dictionary

        Returns:
            Dictionary mapping column names to descriptions

        Raises:
            ValueError: If metadata is malformed or descriptions are too long
        """
        if not metadata:
            return {}

        column_descriptions = {}

        # Extract schema from metadata
        schema = metadata.get("schema", [])
        if schema is None:
            # For incremental materialization, schema might be None
            return {}
        if not isinstance(schema, list):
            raise ValueError("Schema must be a list of column definitions")

        for col_def in schema:
            if not isinstance(col_def, dict):
                raise ValueError("Each column definition must be a dictionary")

            if "name" not in col_def:
                raise ValueError("Column definition must include 'name' field")

            col_name = col_def["name"]
            description = col_def.get("description")

            if description:
                # Validate description length (most databases have limits around 4000 chars)
                if len(description) > 4000:
                    raise ValueError(
                        f"Column description for '{col_name}' is too long (max 4000 characters, got {len(description)})"
                    )

                column_descriptions[col_name] = description

        return column_descriptions

    def _add_column_comments(self, table_name: str, column_descriptions: dict[str, str]) -> None:
        """
        Add column comments to a table.

        Args:
            table_name: Name of the table
            column_descriptions: Dictionary mapping column names to descriptions
        """
        for col_name, description in column_descriptions.items():
            try:
                # Most databases use COMMENT ON COLUMN syntax
                comment_query = f"COMMENT ON COLUMN {table_name}.{col_name} IS '{description.replace("'", "''")}'"
                self.connection.execute(comment_query)
                self.logger.debug(f"Added comment to column {table_name}.{col_name}")
            except Exception as e:
                self.logger.warning(f"Could not add comment to column {table_name}.{col_name}: {e}")
                # Continue with other columns even if one fails

    def _add_table_comment(self, table_name: str, description: str) -> None:
        """
        Add a comment to a table.

        Args:
            table_name: Name of the table
            description: Description of the table
        """
        try:
            # Most databases use COMMENT ON TABLE syntax
            comment_query = f"COMMENT ON TABLE {table_name} IS '{description.replace("'", "''")}'"
            self.connection.execute(comment_query)
            self.logger.debug(f"Added comment to table {table_name}")
        except Exception as e:
            self.logger.warning(f"Could not add comment to table {table_name}: {e}")
            # Don't raise here - table creation succeeded, comments are optional
