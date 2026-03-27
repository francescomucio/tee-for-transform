"""
PostgreSQL adapter implementation.

This module provides PostgreSQL-specific functionality including:
- SQL dialect conversion
- PostgreSQL-specific optimizations
- Connection management
- Materialization support
"""

import importlib.util
import uuid
from typing import Any

from tee.adapters.base import AdapterConfig, DatabaseAdapter, MaterializationType
from tee.adapters.registry import register_adapter


class PostgreSQLAdapter(DatabaseAdapter):
    """PostgreSQL database adapter with SQLglot integration."""

    def __init__(self, config: AdapterConfig) -> None:
        if importlib.util.find_spec("psycopg2") is None:
            raise ImportError(
                "psycopg2 is not installed. Install it with: uv add psycopg2-binary"
            ) from None

        super().__init__(config)

    def get_default_dialect(self) -> str:
        """Get the default SQL dialect for PostgreSQL."""
        return "postgresql"

    def get_supported_materializations(self) -> list[MaterializationType]:
        """Get list of supported materialization types for PostgreSQL."""
        return [
            MaterializationType.TABLE,
            MaterializationType.VIEW,
            MaterializationType.MATERIALIZED_VIEW,
        ]

    def connect(self) -> None:
        """Establish connection to PostgreSQL database."""
        if not all(
            [self.config.host, self.config.user, self.config.password, self.config.database]
        ):
            raise ValueError("PostgreSQL connection requires host, user, password, and database")

        connection_params = {
            "host": self.config.host,
            "port": self.config.port or 5432,
            "database": self.config.database,
            "user": self.config.user,
            "password": self.config.password,
        }

        try:
            import psycopg2

            self.connection = psycopg2.connect(**connection_params)
            self.logger.info(
                f"Connected to PostgreSQL: {self.config.host}:{self.config.port}/{self.config.database}"
            )
        except Exception as e:
            self.logger.error(f"Failed to connect to PostgreSQL: {e}")
            raise

    def disconnect(self) -> None:
        """Close the PostgreSQL connection."""
        if self.connection:
            self.connection.close()
            self.connection = None
            self.logger.info("Disconnected from PostgreSQL database")

    def execute_query(self, query: str) -> Any:
        """Execute a SQL query and return results."""
        if not self.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        try:
            cursor = self.connection.cursor()
            cursor.execute(query)
            result = cursor.fetchall()
            cursor.close()
            self.logger.debug(f"Executed query: {query[:100]}...")
            return result
        except Exception as e:
            self.logger.error(f"Error executing query: {e}")
            raise

    def create_table(
        self,
        table_name: str,
        query: str,
        metadata: dict[str, Any] | None = None,  # noqa: ARG002
    ) -> None:
        """Create a table from a qualified SQL query."""
        if not self.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        # Convert SQL if needed
        converted_query = self.convert_sql_dialect(query)

        # Qualify table references if schema is specified
        if self.config.schema:
            converted_query = self.qualify_table_references(converted_query, self.config.schema)

        # Extract schema and table name
        if "." in table_name:
            schema_name, _ = table_name.split(".", 1)
            # Create schema if it doesn't exist
            try:
                cursor = self.connection.cursor()
                cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_name}")
                self.connection.commit()
                cursor.close()
                self.logger.debug(f"Created schema: {schema_name}")
            except Exception as e:
                self.logger.warning(f"Could not create schema {schema_name}: {e}")

        # Wrap the query in a CREATE TABLE statement
        create_query = f"CREATE TABLE IF NOT EXISTS {table_name} AS {converted_query}"

        try:
            cursor = self.connection.cursor()
            cursor.execute(create_query)
            self.connection.commit()
            cursor.close()
            self.logger.info(f"Created table: {table_name}")
        except Exception as e:
            self.logger.error(f"Failed to create table {table_name}: {e}")
            raise

    def create_view(
        self, view_name: str, query: str, metadata: dict[str, Any] | None = None
    ) -> None:
        """Create a view from a qualified SQL query."""
        if not self.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        # Convert SQL if needed
        converted_query = self.convert_sql_dialect(query)

        # Qualify table references if schema is specified
        if self.config.schema:
            converted_query = self.qualify_table_references(converted_query, self.config.schema)

        # Extract schema and view name
        if "." in view_name:
            schema_name, _ = view_name.split(".", 1)
            # Create schema if it doesn't exist
            try:
                cursor = self.connection.cursor()
                cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_name}")
                self.connection.commit()
                cursor.close()
                self.logger.debug(f"Created schema: {schema_name}")
            except Exception as e:
                self.logger.warning(f"Could not create schema {schema_name}: {e}")

        # Wrap the query in a CREATE VIEW statement
        create_query = f"CREATE OR REPLACE VIEW {view_name} AS {converted_query}"

        try:
            cursor = self.connection.cursor()
            cursor.execute(create_query)
            self.connection.commit()
            cursor.close()
            self.logger.info(f"Created view: {view_name}")

            # Add view and column comments if metadata is provided
            if metadata:
                # Add view description
                if "description" in metadata and metadata["description"]:
                    self._add_table_comment(view_name, metadata["description"])

                # Add column comments
                if "schema" in metadata and metadata["schema"]:
                    column_descriptions = self._validate_column_metadata(metadata)
                    if column_descriptions:
                        self._add_column_comments(view_name, column_descriptions)

        except Exception as e:
            self.logger.error(f"Failed to create view {view_name}: {e}")
            raise

    def create_materialized_view(self, view_name: str, query: str) -> None:
        """Create a materialized view from a qualified SQL query."""
        if not self.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        # Convert SQL if needed
        converted_query = self.convert_sql_dialect(query)

        # Qualify table references if schema is specified
        if self.config.schema:
            converted_query = self.qualify_table_references(converted_query, self.config.schema)

        # Extract schema and view name
        if "." in view_name:
            schema_name, _ = view_name.split(".", 1)
            # Create schema if it doesn't exist
            try:
                cursor = self.connection.cursor()
                cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_name}")
                self.connection.commit()
                cursor.close()
                self.logger.debug(f"Created schema: {schema_name}")
            except Exception as e:
                self.logger.warning(f"Could not create schema {schema_name}: {e}")

        # PostgreSQL materialized view syntax
        create_query = f"CREATE MATERIALIZED VIEW IF NOT EXISTS {view_name} AS {converted_query}"

        try:
            cursor = self.connection.cursor()
            cursor.execute(create_query)
            self.connection.commit()
            cursor.close()
            self.logger.info(f"Created materialized view: {view_name}")
        except Exception as e:
            self.logger.error(f"Failed to create materialized view {view_name}: {e}")
            raise

    def table_exists(self, table_name: str) -> bool:
        """Check if a table or view exists in the database."""
        if not self.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        try:
            # Extract schema and table name
            if "." in table_name:
                parts = table_name.split(".", 1)
                schema_name = parts[0]
                table_name_only = parts[1]
            else:
                schema_name = self.config.schema or "public"
                table_name_only = table_name

            cursor = self.connection.cursor()
            # Check both tables and views (like Snowflake)
            cursor.execute(
                """
                SELECT COUNT(*) FROM (
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = %s AND table_name = %s
                    UNION ALL
                    SELECT table_name FROM information_schema.views
                    WHERE table_schema = %s AND table_name = %s
                )
                """,
                (schema_name, table_name_only, schema_name, table_name_only),
            )
            result = cursor.fetchone()
            cursor.close()
            return result[0] > 0 if result else False
        except Exception:
            return False

    def drop_table(self, table_name: str) -> None:
        """Drop a table from the database."""
        if not self.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        try:
            cursor = self.connection.cursor()
            cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
            self.connection.commit()
            cursor.close()
            self.logger.info(f"Dropped table: {table_name}")
        except Exception as e:
            self.logger.error(f"Error dropping table {table_name}: {e}")
            raise

    def get_table_info(self, table_name: str) -> dict[str, Any]:
        """Get information about a table."""
        if not self.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        try:
            # Extract schema and table name
            if "." in table_name:
                parts = table_name.split(".", 1)
                schema_name = parts[0]
                table_name_only = parts[1]
            else:
                schema_name = self.config.schema or "public"
                table_name_only = table_name

            cursor = self.connection.cursor()

            # Get table schema (filter by schema like Snowflake)
            cursor.execute(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                ORDER BY ordinal_position
            """,
                (schema_name, table_name_only),
            )
            schema_result = cursor.fetchall()

            # Get row count
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count_result = cursor.fetchone()

            cursor.close()

            return {
                "schema": [{"column": row[0], "type": row[1]} for row in schema_result],
                "row_count": count_result[0] if count_result else 0,
            }
        except Exception as e:
            self.logger.error(f"Error getting table info for {table_name}: {e}")
            raise

    def describe_query_schema(self, sql_query: str) -> list[dict[str, Any]]:
        """Infer schema from SQL query output using PostgreSQL temporary table."""
        if not self.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        # Use temporary table approach for accurate type information (similar to Snowflake)
        temp_table_name = f"temp_schema_infer_{uuid.uuid4().hex[:8]}"

        try:
            cursor = self.connection.cursor()
            # Create temporary table with LIMIT 0 to get schema without data
            create_temp_sql = f"CREATE TEMP TABLE {temp_table_name} AS {sql_query} LIMIT 0"
            cursor.execute(create_temp_sql)

            # Query information_schema to get column types
            cursor.execute(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = %s
                ORDER BY ordinal_position
                """,
                (temp_table_name,),
            )
            result = cursor.fetchall()

            # Convert to standard format: [{"name": "...", "type": "..."}]
            schema = []
            for row in result:
                schema.append({"name": row[0], "type": row[1]})

            # Drop temporary table
            cursor.execute(f"DROP TABLE IF EXISTS {temp_table_name}")
            self.connection.commit()
            cursor.close()

            return schema
        except Exception as e:
            # Cleanup on error
            try:
                if self.connection:
                    cursor = self.connection.cursor()
                    cursor.execute(f"DROP TABLE IF EXISTS {temp_table_name}")
                    self.connection.commit()
                    cursor.close()
            except Exception:
                pass
            self.logger.error(f"Error describing query schema: {e}")
            raise

    def add_column(self, table_name: str, column: dict[str, Any]) -> None:
        """Add a column to an existing table."""
        if not self.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        column_name = column["name"]
        column_type = column.get("type", "VARCHAR")

        try:
            ddl = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
            cursor = self.connection.cursor()
            cursor.execute(ddl)
            self.connection.commit()
            cursor.close()
            self.logger.info(f"Added column {column_name} to {table_name}")
        except Exception as e:
            self.logger.error(f"Error adding column {column_name} to {table_name}: {e}")
            raise

    def drop_column(self, table_name: str, column_name: str) -> None:
        """Drop a column from an existing table."""
        if not self.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        try:
            ddl = f"ALTER TABLE {table_name} DROP COLUMN {column_name}"
            cursor = self.connection.cursor()
            cursor.execute(ddl)
            self.connection.commit()
            cursor.close()
            self.logger.info(f"Dropped column {column_name} from {table_name}")
        except Exception as e:
            self.logger.error(f"Error dropping column {column_name} from {table_name}: {e}")
            raise

    def create_function(
        self,
        function_name: str,
        function_sql: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Create or replace a user-defined function in the database."""
        if not self.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        # Create schema if needed
        if "." in function_name:
            schema_name, _ = function_name.split(".", 1)
            try:
                cursor = self.connection.cursor()
                cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_name}")
                self.connection.commit()
                cursor.close()
                self.logger.debug(f"Created schema: {schema_name}")
            except Exception as e:
                self.logger.warning(f"Could not create schema {schema_name}: {e}")

        # Function SQL is already a complete CREATE OR REPLACE FUNCTION statement
        # Execute it as-is (should already be in PostgreSQL dialect)
        try:
            cursor = self.connection.cursor()
            cursor.execute(function_sql)
            self.connection.commit()
            cursor.close()
            self.logger.info(f"Created function: {function_name}")

            # Attach tags if provided (PostgreSQL doesn't natively support tags, but log debug)
            if metadata:
                tags = metadata.get("tags", [])
                object_tags = metadata.get("object_tags", {})
                if tags:
                    self.attach_tags("FUNCTION", function_name, tags)
                if object_tags:
                    self.attach_object_tags("FUNCTION", function_name, object_tags)

        except Exception as e:
            self.logger.error(f"Failed to create function {function_name}: {e}")
            from tee.parser.shared.exceptions import FunctionExecutionError

            raise FunctionExecutionError(f"Failed to create function {function_name}: {e}") from e

    def function_exists(
        self,
        function_name: str,
        signature: str | None = None,  # noqa: ARG002
    ) -> bool:
        """Check if a function exists in the database."""
        if not self.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        try:
            # Extract schema and function name
            if "." in function_name:
                schema_name, func_name = function_name.split(".", 1)
            else:
                schema_name = "public"  # PostgreSQL default schema
                func_name = function_name

            # Query information_schema.routines for functions
            cursor = self.connection.cursor()
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM information_schema.routines
                WHERE routine_schema = %s AND routine_name = %s AND routine_type = 'FUNCTION'
                """,
                [schema_name, func_name],
            )
            result = cursor.fetchone()
            cursor.close()
            return result[0] > 0 if result else False
        except Exception as e:
            self.logger.warning(f"Error checking if function {function_name} exists: {e}")
            return False

    def drop_function(self, function_name: str) -> None:
        """Drop a function from the database."""
        if not self.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        try:
            # PostgreSQL requires the full signature for DROP FUNCTION
            # For now, we'll use DROP FUNCTION IF EXISTS with just the name
            # This may fail if there are multiple overloads - that's expected behavior
            cursor = self.connection.cursor()
            cursor.execute(f"DROP FUNCTION IF EXISTS {function_name}")
            self.connection.commit()
            cursor.close()
            self.logger.info(f"Dropped function: {function_name}")
        except Exception as e:
            self.logger.error(f"Error dropping function {function_name}: {e}")
            from tee.parser.shared.exceptions import FunctionExecutionError

            raise FunctionExecutionError(f"Failed to drop function {function_name}: {e}") from e


# Register the adapter
register_adapter("postgresql", PostgreSQLAdapter)
