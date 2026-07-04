"""Function management for DuckDB."""

import logging
from contextlib import suppress
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from t4t.adapters.base.core import DatabaseAdapter

logger = logging.getLogger(__name__)


class FunctionManager:
    """Manages function creation and existence checking for DuckDB."""

    def __init__(self, adapter: DatabaseAdapter) -> None:
        """
        Initialize the function manager.

        Args:
            adapter: DuckDBAdapter instance
        """
        self.adapter = adapter
        self.config = adapter.config
        self.logger = adapter.logger

    def create(
        self,
        function_name: str,
        function_sql: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Create or replace a user-defined function in the database."""
        if not self.adapter.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        # Create schema if needed
        self.adapter.utils.create_schema_if_needed(function_name)

        # For DuckDB, macros need to be created in the schema context
        # Extract schema name and set context if needed
        schema_name = None
        if "." in function_name:
            schema_name, _ = function_name.split(".", 1)
            # Set schema context before creating macro
            try:
                self.adapter.connection.execute(f"USE {schema_name}")
                self.logger.debug(f"Set schema context to: {schema_name}")
            except Exception as e:
                self.logger.warning(f"Could not set schema context to {schema_name}: {e}")

        # Function SQL is already a complete CREATE OR REPLACE FUNCTION/MACRO statement
        # Execute it as-is (no conversion needed, as it should already be in DuckDB dialect)
        try:
            # Execute the CREATE OR REPLACE FUNCTION/MACRO statement
            self.adapter.utils.execute_query(function_sql)
            self.logger.info(f"Created function: {function_name}")

            # Reset to main schema if we changed context
            if schema_name:
                with suppress(Exception):
                    self.adapter.connection.execute("USE main")

            # Attach tags if provided and supported (DuckDB doesn't support tags, but we log)
            if metadata:
                tags = metadata.get("tags", [])
                object_tags = metadata.get("object_tags", {})
                if tags:
                    self.adapter.attach_tags("FUNCTION", function_name, tags)
                if object_tags:
                    self.adapter.attach_object_tags("FUNCTION", function_name, object_tags)

        except Exception as e:
            self.logger.error(f"Failed to create function {function_name}: {e}")
            from t4t.parser.shared.exceptions import FunctionExecutionError

            raise FunctionExecutionError(f"Failed to create function {function_name}: {e}") from e

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

        # Extract schema and function name
        if "." in function_name:
            schema_name, func_name = function_name.split(".", 1)
        else:
            schema_name = "main"  # DuckDB default schema
            func_name = function_name

        # Try information_schema first (if available)
        if self._check_function_via_information_schema(schema_name, func_name, signature):
            return True

        # Fallback to SHOW commands (for in-memory databases where information_schema isn't available)
        return self._check_function_via_show_commands(schema_name, func_name)

    def _check_function_via_information_schema(
        self, schema_name: str, func_name: str, signature: str | None = None
    ) -> bool:
        """Check function existence via information_schema (may not be available in all contexts)."""
        try:
            if signature:
                # Try to match exact signature
                sig_types = [t.strip().upper() for t in signature.split(",")]
                query = """
                    SELECT COUNT(*)
                    FROM information_schema.routines r
                    WHERE r.routine_schema = ?
                      AND r.routine_name = ?
                      AND r.routine_type = 'FUNCTION'
                      AND (
                          SELECT COUNT(*)
                          FROM information_schema.parameters p
                          WHERE p.specific_schema = r.routine_schema
                            AND p.specific_name = r.specific_name
                            AND p.parameter_mode = 'IN'
                          GROUP BY p.specific_schema, p.specific_name
                          HAVING COUNT(*) = ?
                            AND GROUP_CONCAT(UPPER(p.data_type) ORDER BY p.ordinal_position) = ?
                      ) > 0
                """
                sig_str = ", ".join(sig_types)
                result = self.adapter.connection.execute(
                    query, [schema_name, func_name, len(sig_types), sig_str]
                ).fetchone()
                if result and result[0] > 0:
                    return True
                # If signature match fails, fall through to name-only check

            # Name-only check
            query = """
                SELECT COUNT(*)
                FROM information_schema.routines
                WHERE routine_schema = ? AND routine_name = ? AND routine_type = 'FUNCTION'
            """
            result = self.adapter.connection.execute(query, [schema_name, func_name]).fetchone()
            return result[0] > 0 if result else False
        except Exception:
            # information_schema not available in this context
            return False

    def _check_function_via_show_commands(self, schema_name: str, func_name: str) -> bool:
        """Check function existence via SHOW MACROS/FUNCTIONS (fallback for in-memory databases)."""
        schema_changed = False
        try:
            # Set schema context if needed
            if schema_name != "main":
                self.adapter.connection.execute(f"USE {schema_name}")
                schema_changed = True

            # Try SHOW MACROS (for SQL macros)
            try:
                result = self.adapter.connection.execute(
                    f"SHOW MACROS LIKE '{func_name}'"
                ).fetchall()
                if result:
                    return True
            except Exception:
                pass

            # Try SHOW FUNCTIONS (for Python UDFs)
            try:
                result = self.adapter.connection.execute(
                    f"SHOW FUNCTIONS LIKE '{func_name}'"
                ).fetchall()
                if result:
                    return True
            except Exception:
                pass

            return False
        finally:
            # Reset schema context
            if schema_changed:
                with suppress(Exception):
                    self.adapter.connection.execute("USE main")

    def drop(self, function_name: str) -> None:
        """Drop a function from the database."""
        if not self.adapter.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        try:
            # DuckDB uses DROP FUNCTION with signature, but we'll use a simple approach
            # Extract function name (without schema for DROP)
            if "." in function_name:
                _, func_name = function_name.split(".", 1)
            else:
                func_name = function_name

            # Note: DuckDB requires the full signature for DROP FUNCTION
            # For now, we'll use DROP FUNCTION IF EXISTS with just the name
            # This may fail if there are multiple overloads - that's expected behavior
            self.adapter.utils.execute_query(f"DROP FUNCTION IF EXISTS {func_name}")
            self.logger.info(f"Dropped function: {func_name}")
        except Exception as e:
            self.logger.error(f"Error dropping function {function_name}: {e}")
            from t4t.parser.shared.exceptions import FunctionExecutionError

            raise FunctionExecutionError(f"Failed to drop function {function_name}: {e}") from e
