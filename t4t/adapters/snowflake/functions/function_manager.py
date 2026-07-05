"""Function management for Snowflake."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from t4t.adapters.base.core import DatabaseAdapter

logger = logging.getLogger(__name__)


class FunctionManager:
    """Manages function creation and existence checking for Snowflake."""

    def __init__(self, adapter: DatabaseAdapter) -> None:
        """
        Initialize the function manager.

        Args:
            adapter: SnowflakeAdapter instance
        """
        self.adapter = adapter
        self.config = adapter.config
        self.logger = adapter.logger
        self.tag_manager = adapter.tag_manager

    def create(
        self,
        function_name: str,
        function_sql: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Create or replace a user-defined function in the database."""
        if not self.adapter.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        # Create schema if needed (schema tags will be handled by execution engine)
        self.adapter.utils.create_schema_if_needed(function_name)

        # Use 3-part naming for the function (DATABASE.SCHEMA.FUNCTION)
        qualified_function_name = self.adapter.utils.qualify_object_name(function_name)

        # Replace function name in SQL with qualified name if needed
        # Extract unqualified function name from function_sql and replace with qualified
        # Pattern to match CREATE OR REPLACE FUNCTION function_name(
        pattern = r"(CREATE\s+OR\s+REPLACE\s+FUNCTION\s+)([a-zA-Z_][a-zA-Z0-9_]*)\s*\("
        if re.search(pattern, function_sql, re.IGNORECASE):
            # Replace function name with qualified name
            qualified_sql = re.sub(
                pattern,
                rf"\1{qualified_function_name}(",
                function_sql,
                flags=re.IGNORECASE,
            )
        else:
            # If pattern doesn't match, use SQL as-is (might already have qualified name)
            qualified_sql = function_sql

        try:
            # Execute the CREATE OR REPLACE FUNCTION statement
            self.adapter.utils.execute_with_cursor(qualified_sql)
            self.logger.info(f"Created function: {qualified_function_name}")

            # Attach tags if provided (Snowflake supports full tag functionality)
            if metadata:
                tags = metadata.get("tags", [])
                object_tags = metadata.get("object_tags", {})
                if tags:
                    self.tag_manager.attach_tags("FUNCTION", qualified_function_name, tags)
                if object_tags:
                    self.tag_manager.attach_object_tags(
                        "FUNCTION", qualified_function_name, object_tags
                    )

        except Exception as e:
            self.logger.error(f"Failed to create function {qualified_function_name}: {e}")
            from t4t.parser.shared.exceptions import FunctionExecutionError

            raise FunctionExecutionError(
                f"Failed to create function {qualified_function_name}: {e}"
            ) from e

    def exists(self, function_name: str, signature: str | None = None) -> bool:
        """
        Check if a function exists in the database.

        Args:
            function_name: Name of the function (can be qualified: schema.function_name)
            signature: Optional function signature (e.g., "FLOAT, FLOAT" for parameters)
                      If provided, checks for exact signature match (handles overloading)

        Returns:
            True if function exists (and matches signature if provided), False otherwise
        """
        if not self.adapter.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        try:
            # Extract schema and function name
            if "." in function_name:
                parts = function_name.split(".")
                func_name = parts[-1]
                schema_name = parts[-2] if len(parts) >= 2 else self.config.schema or "PUBLIC"
            else:
                schema_name = self.config.schema or "PUBLIC"
                func_name = function_name

            cursor = self.adapter.connection.cursor()
            try:
                # If signature is provided, use DESCRIBE FUNCTION with signature for exact match
                if signature:
                    qualified_name = self.adapter.utils.qualify_object_name(function_name)
                    # DESCRIBE FUNCTION requires the full signature: function_name(param_type1, param_type2, ...)
                    describe_query = f"DESCRIBE FUNCTION {qualified_name}({signature})"
                    try:
                        cursor.execute(describe_query)
                        cursor.fetchall()  # Consume the result
                        return True
                    except Exception:
                        # Function with this signature doesn't exist
                        return False

                # Otherwise, use SHOW FUNCTIONS to check if any function with this name exists
                show_query = (
                    f"SHOW FUNCTIONS LIKE '{func_name.replace("'", "''")}' IN SCHEMA {schema_name}"
                )
                cursor.execute(show_query)
                result = cursor.fetchall()
                # SHOW FUNCTIONS returns a result set - if any rows are returned, the function exists
                if result:
                    # The function name is typically in the 'name' column or first column
                    # Check all columns for a match
                    for row in result:
                        for col in row:
                            if col and str(col).upper() == func_name.upper():
                                return True
                return False
            finally:
                cursor.close()
        except Exception as e:
            self.logger.warning(f"Error checking if function {function_name} exists: {e}")
            return False

    def drop(self, function_name: str) -> None:
        """Drop a function from the database."""
        if not self.adapter.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        try:
            qualified_function_name = self.adapter.utils.qualify_object_name(function_name)
            cursor = self.adapter.connection.cursor()
            try:
                # Snowflake requires the full function signature for DROP FUNCTION
                # Since we don't have it here, we'll use a simple approach
                # This may fail if there are multiple overloads - that's expected behavior
                drop_query = f"DROP FUNCTION IF EXISTS {qualified_function_name}"
                cursor.execute(drop_query)
                self.logger.info(f"Dropped function: {qualified_function_name}")
            finally:
                cursor.close()
        except Exception as e:
            self.logger.error(f"Error dropping function {function_name}: {e}")
            from t4t.parser.shared.exceptions import FunctionExecutionError

            raise FunctionExecutionError(f"Failed to drop function {function_name}: {e}") from e
