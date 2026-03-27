"""
Snowflake adapter with SQLglot integration.

This adapter provides Snowflake-specific functionality including:
- SQL dialect conversion from other dialects to Snowflake
- Snowflake-specific optimizations and features
- Connection management with warehouse and role support
- Materialization support including external tables
"""

import re
import uuid
from typing import Any

try:
    import snowflake.connector
except ImportError:
    snowflake = None

try:
    import sqlglot
except ImportError:
    sqlglot = None

from tee.adapters.base import AdapterConfig, DatabaseAdapter, MaterializationType
from tee.adapters.registry import register_adapter

from .functions.function_manager import FunctionManager
from .materialization.incremental_handler import IncrementalHandler
from .materialization.table_handler import TableHandler
from .materialization.view_handler import ViewHandler
from .tags.tag_manager import TagManager
from .utils.helpers import SnowflakeUtils


class SnowflakeAdapter(DatabaseAdapter):
    """Snowflake database adapter with SQLglot integration."""

    # Snowflake-specific required fields
    REQUIRED_FIELDS = ["type", "user", "password", "database"]

    def __init__(self, config_dict: dict[str, Any]) -> None:
        if snowflake is None:
            raise ImportError(
                "Snowflake connector is not installed. Install it with: uv add snowflake-connector-python"
            )

        super().__init__(config_dict)

        # Initialize component managers
        self.tag_manager = TagManager(self)
        self.function_manager = FunctionManager(self)
        self.table_handler = TableHandler(self)
        self.view_handler = ViewHandler(self)
        self.incremental_handler = IncrementalHandler(self)
        self.utils = SnowflakeUtils(self)

    def _validate_field_values(self, config_dict: dict[str, Any]) -> None:
        """Validate Snowflake-specific field values."""
        super()._validate_field_values(config_dict)

        # Validate account format
        if "account" in config_dict:
            account = config_dict["account"]
            if not isinstance(account, str) or not account.strip():
                raise ValueError("Snowflake account must be a non-empty string")

        # Validate warehouse if provided
        if (
            "warehouse" in config_dict
            and config_dict["warehouse"]
            and (
                not isinstance(config_dict["warehouse"], str)
                or not config_dict["warehouse"].strip()
            )
        ):
            raise ValueError("Snowflake warehouse must be a non-empty string")

        # Validate role if provided
        if (
            "role" in config_dict
            and config_dict["role"]
            and (not isinstance(config_dict["role"], str) or not config_dict["role"].strip())
        ):
            raise ValueError("Snowflake role must be a non-empty string")

    def _create_adapter_config(self, config_dict: dict[str, Any]) -> AdapterConfig:
        """Create Snowflake-specific AdapterConfig."""
        # Prepare extra fields for Snowflake-specific settings
        extra_fields = {}
        if config_dict.get("account"):
            extra_fields["account"] = config_dict.get("account")
        if config_dict.get("extra"):
            extra_fields.update(config_dict.get("extra"))

        return AdapterConfig(
            type=config_dict["type"],
            host=config_dict.get("host"),
            port=config_dict.get("port"),
            database=config_dict.get("database"),
            user=config_dict.get("user"),
            password=config_dict.get("password"),
            path=config_dict.get("path"),
            source_dialect=config_dict.get("source_dialect"),
            target_dialect=config_dict.get("target_dialect"),
            connection_timeout=config_dict.get("connection_timeout", 30),
            query_timeout=config_dict.get("query_timeout", 300),
            schema=config_dict.get("schema"),
            warehouse=config_dict.get("warehouse"),
            role=config_dict.get("role"),
            project=config_dict.get("project"),
            extra=extra_fields if extra_fields else None,
        )

    def get_default_dialect(self) -> str:
        """Get the default SQL dialect for Snowflake."""
        return "snowflake"

    def get_supported_materializations(self) -> list[MaterializationType]:
        """Get list of supported materialization types for Snowflake."""
        return [
            MaterializationType.TABLE,
            MaterializationType.VIEW,
            MaterializationType.INCREMENTAL,
        ]

    def connect(self) -> None:
        """Establish connection to Snowflake database."""
        if not all(
            [self.config.host, self.config.user, self.config.password, self.config.database]
        ):
            raise ValueError("Snowflake connection requires host, user, password, and database")

        # Get account from extra fields or extract from host
        account = self.config.host
        if self.config.extra and "account" in self.config.extra:
            account = self.config.extra["account"]
        else:
            # Extract account from host (e.g., "IZOMIWY-AM07852.snowflakecomputing.com" -> "IZOMIWY-AM07852")
            if self.config.host and ".snowflakecomputing.com" in self.config.host:
                account = self.config.host.replace(".snowflakecomputing.com", "")

        connection_params = {
            "account": account,
            "user": self.config.user,
            "password": self.config.password,
            "database": self.config.database,
            "warehouse": self.config.warehouse,
            "role": self.config.role,
            "schema": self.config.schema,
        }

        # Remove None values
        connection_params = {k: v for k, v in connection_params.items() if v is not None}

        try:
            self.connection = snowflake.connector.connect(**connection_params)
            self.logger.info(f"Connected to Snowflake: {self.config.host}/{self.config.database}")
        except Exception as e:
            self.logger.error(f"Failed to connect to Snowflake: {e}")
            raise

    def disconnect(self) -> None:
        """Close the Snowflake connection."""
        if self.connection:
            self.connection.close()
            self.connection = None
            self.logger.info("Disconnected from Snowflake database")

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
        self, table_name: str, query: str, metadata: dict[str, Any] | None = None
    ) -> None:
        """Create a table from a qualified SQL query with optional column metadata."""
        self.table_handler.create(table_name, query, metadata)

    def create_view(
        self, view_name: str, query: str, metadata: dict[str, Any] | None = None
    ) -> None:
        """Create a view from a qualified SQL query."""
        self.view_handler.create(view_name, query, metadata)

    def table_exists(self, table_name: str) -> bool:
        """Check if a table or view exists in the database."""
        if not self.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        try:
            # Extract schema and table name for the query
            if "." in table_name:
                parts = table_name.split(".", 1)
                schema_name = parts[0]
                table_name_only = parts[1]
            else:
                schema_name = self.config.schema or "PUBLIC"
                table_name_only = table_name

            # Check both tables and views (Snowflake stores views separately)
            # Snowflake connector uses %s parameter style
            result = self._execute_with_cursor(
                """
                SELECT COUNT(*) FROM (
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = %s AND table_name = %s
                    UNION ALL
                    SELECT table_name FROM information_schema.views
                    WHERE table_schema = %s AND table_name = %s
                )
                """,
                (
                    schema_name.upper(),
                    table_name_only.upper(),
                    schema_name.upper(),
                    table_name_only.upper(),
                ),
            )
            return result[0][0] > 0
        except Exception:
            return False

    def get_table_info(self, table_name: str) -> dict[str, Any]:
        """Get information about a table."""
        if not self.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        try:
            # Use 3-part naming for Snowflake (DATABASE.SCHEMA.TABLE)
            qualified_table_name = self._qualify_object_name(table_name)

            # Extract schema and table name for the query
            if "." in table_name:
                parts = table_name.split(".", 1)
                schema_name = parts[0]
                table_name_only = parts[1]
            else:
                schema_name = self.config.schema or "PUBLIC"
                table_name_only = table_name

            schema_result = self._execute_with_cursor(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                ORDER BY ordinal_position
            """,
                (schema_name.upper(), table_name_only.upper()),
            )

            # Get row count
            count_result = self._execute_with_cursor(f"SELECT COUNT(*) FROM {qualified_table_name}")

            return {
                "schema": [{"column": row[0], "type": row[1]} for row in schema_result],
                "row_count": count_result[0][0] if count_result else 0,
            }
        except Exception as e:
            self.logger.error(f"Error getting table info for {table_name}: {e}")
            raise

    def describe_query_schema(self, sql_query: str) -> list[dict[str, Any]]:
        """Infer schema from SQL query output using Snowflake DESCRIBE."""
        if not self.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        try:
            # Snowflake approach: Create a temporary view, describe it, then drop it
            # Use a unique name to avoid conflicts
            temp_view_name = f"TEMP_SCHEMA_INFER_{uuid.uuid4().hex[:8].upper()}"
            qualified_temp_view = self._qualify_object_name(temp_view_name)

            cursor = self.connection.cursor()
            try:
                # Remove LIMIT clause from query if present (to avoid "LIMIT ... LIMIT 0" syntax error)
                # We'll add our own LIMIT 0
                # Remove trailing LIMIT clause (case-insensitive)
                query_without_limit = re.sub(
                    r"\s+LIMIT\s+\d+\s*$", "", sql_query.strip(), flags=re.IGNORECASE
                )
                # Create temporary view with LIMIT 0 to avoid data processing
                create_view_sql = f"CREATE OR REPLACE TEMPORARY VIEW {qualified_temp_view} AS {query_without_limit} LIMIT 0"
                cursor.execute(create_view_sql)

                # Describe the view to get schema
                describe_sql = f"DESCRIBE {qualified_temp_view}"
                cursor.execute(describe_sql)
                result = cursor.fetchall()

                # Convert to standard format: [{"name": "...", "type": "..."}]
                schema = []
                for row in result:
                    # DESCRIBE returns: name, type, kind, null?, default, primary key?, unique key?, check, expression, comment
                    schema.append({"name": row[0], "type": row[1]})

                # Drop the temporary view
                cursor.execute(f"DROP VIEW IF EXISTS {qualified_temp_view}")

                return schema
            finally:
                cursor.close()
        except Exception as e:
            self.logger.error(f"Error describing query schema: {e}")
            raise

    def add_column(self, table_name: str, column: dict[str, Any]) -> None:
        """Add a column to an existing table."""
        if not self.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        column_name = column["name"]
        column_type = column.get("type", "VARCHAR")

        try:
            # Use 3-part naming for Snowflake
            qualified_table_name = self._qualify_object_name(table_name)

            # Snowflake ALTER TABLE ADD COLUMN syntax
            ddl = f"ALTER TABLE {qualified_table_name} ADD COLUMN {column_name} {column_type}"
            cursor = self.connection.cursor()
            try:
                cursor.execute(ddl)
                self.logger.info(f"Added column {column_name} to {table_name}")
            finally:
                cursor.close()
        except Exception as e:
            self.logger.error(f"Error adding column {column_name} to {table_name}: {e}")
            raise

    def drop_column(self, table_name: str, column_name: str) -> None:
        """Drop a column from an existing table."""
        if not self.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        try:
            # Use 3-part naming for Snowflake
            qualified_table_name = self._qualify_object_name(table_name)

            # Snowflake ALTER TABLE DROP COLUMN syntax
            ddl = f"ALTER TABLE {qualified_table_name} DROP COLUMN {column_name}"
            cursor = self.connection.cursor()
            try:
                cursor.execute(ddl)
                self.logger.info(f"Dropped column {column_name} from {table_name}")
            finally:
                cursor.close()
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
        self.function_manager.create(function_name, function_sql, metadata)

    def function_exists(self, function_name: str, signature: str | None = None) -> bool:
        """Check if a function exists in the database."""
        return self.function_manager.exists(function_name, signature)

    def drop_function(self, function_name: str) -> None:
        """Drop a function from the database."""
        self.function_manager.drop(function_name)

    def get_table_columns(self, table_name: str) -> list[str]:
        """Return ordered column names for a table."""
        if not self.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")
        try:
            # Extract schema and table name for information_schema lookup
            if "." in table_name:
                parts = table_name.split(".", 1)
                if len(parts) == 2:
                    schema_name, table_name_only = parts
                else:
                    schema_name = self.config.schema or "PUBLIC"
                    table_name_only = parts[0]
            else:
                schema_name = self.config.schema or "PUBLIC"
                table_name_only = table_name

            rows = self._execute_with_cursor(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = UPPER(%s) AND table_name = UPPER(%s)
                ORDER BY ordinal_position
                """,
                (schema_name, table_name_only),
            )
            return [r[0] for r in rows]
        except Exception as e:
            self.logger.error(f"Error getting columns for table {table_name}: {e}")
            # Fallback to empty list; callers should handle
            return []

    def qualify_table_references(self, sql: str, schema: str | None = None) -> str:
        """
        Qualify table references with schema names for Snowflake.

        Args:
            sql: SQL query to qualify
            schema: Schema name to use for qualification

        Returns:
            SQL with qualified table references
        """
        if not sql or not sql.strip() or not schema:
            return sql

        if sqlglot is None:
            self.logger.warning("SQLglot not available, skipping table qualification")
            return sql

        try:
            # Parse the SQL
            parsed = sqlglot.parse_one(sql, read=self.target_dialect)

            # For Snowflake, we need to manually qualify table references
            # because the qualify optimizer quotes schema names incorrectly
            qualified_tables = []
            for table in parsed.find_all(sqlglot.exp.Table):
                if not table.name.startswith(schema + "."):
                    # Create a new qualified table reference
                    qualified_name = f"{schema.upper()}.{table.name}"
                    # Replace the table name in the AST
                    table.replace(sqlglot.exp.Table(this=qualified_name))
                    qualified_tables.append(qualified_name)

            # Convert back to SQL
            qualified_sql = parsed.sql(dialect=self.target_dialect)

            # Log qualification
            if qualified_tables:
                self.logger.debug(f"Qualified tables: {qualified_tables}")

            return qualified_sql

        except Exception as e:
            self.logger.warning(f"Failed to qualify table references: {e}")
            return sql

    def get_database_info(self) -> dict[str, Any]:
        """Get Snowflake-specific database information."""
        base_info = super().get_database_info()

        if self.connection:
            try:
                # Get Snowflake version
                version_result = self._execute_with_cursor("SELECT CURRENT_VERSION()")
                base_info["snowflake_version"] = (
                    version_result[0][0] if version_result else "unknown"
                )

                # Get current warehouse
                warehouse_result = self._execute_with_cursor("SELECT CURRENT_WAREHOUSE()")
                base_info["current_warehouse"] = (
                    warehouse_result[0][0] if warehouse_result else "unknown"
                )

                # Get current role
                role_result = self._execute_with_cursor("SELECT CURRENT_ROLE()")
                base_info["current_role"] = role_result[0][0] if role_result else "unknown"

            except Exception as e:
                self.logger.warning(f"Could not get Snowflake-specific info: {e}")

        return base_info

    def drop_table(self, table_name: str) -> None:
        """Drop a table from the database."""
        if not self.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        try:
            cursor = self.connection.cursor()
            cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
            cursor.close()
            self.logger.info(f"Dropped table: {table_name}")
        except Exception as e:
            self.logger.error(f"Error dropping table {table_name}: {e}")
            raise

    def _qualify_object_name(self, object_name: str) -> str:
        """Return DATABASE-prefixed name if not already fully qualified."""
        return self.utils.qualify_object_name(object_name)

    def _create_schema_if_needed(
        self, object_name: str, schema_metadata: dict[str, Any] | None = None
    ) -> None:
        """Create schema if needed for the given object name and attach tags if provided."""
        self.utils.create_schema_if_needed(object_name, schema_metadata)

    def _execute_with_cursor(self, query: str, params: tuple | None = None) -> Any:
        """Execute a query with proper cursor management."""
        return self.utils.execute_with_cursor(query, params)

    def _add_table_comment(self, table_name: str, description: str) -> None:
        """Add a comment to a table using Snowflake's COMMENT ON TABLE syntax."""
        self.utils.add_table_comment(table_name, description)

    def _add_column_comments(self, table_name: str, column_descriptions: dict[str, str]) -> None:
        """Add column comments to a table using Snowflake's COMMENT ON COLUMN syntax."""
        self.utils.add_column_comments(table_name, column_descriptions)

    def execute_incremental_append(self, table_name: str, sql_query: str) -> None:
        """Execute incremental append into an existing table, or create if missing."""
        self.incremental_handler.execute_append(table_name, sql_query)

    def execute_incremental_merge(
        self, table_name: str, source_sql: str, config: dict[str, Any]
    ) -> None:
        """Execute incremental merge (upsert) with dedup and tuple ON for composite keys."""
        self.incremental_handler.execute_merge(table_name, source_sql, config)

    def execute_incremental_delete_insert(
        self, table_name: str, delete_sql: str, insert_sql: str
    ) -> None:
        """Execute delete+insert atomically in a transaction, aligning columns."""
        self.incremental_handler.execute_delete_insert(table_name, delete_sql, insert_sql)

    def attach_tags(self, object_type: str, object_name: str, tags: list[str]) -> None:
        """Attach tags to a Snowflake database object."""
        self.tag_manager.attach_tags(object_type, object_name, tags)

    def attach_object_tags(
        self, object_type: str, object_name: str, object_tags: dict[str, str]
    ) -> None:
        """Attach object tags (key-value pairs) to a Snowflake database object."""
        self.tag_manager.attach_object_tags(object_type, object_name, object_tags)

    def generate_no_duplicates_test_query(
        self, table_name: str, columns: list[str] | None = None
    ) -> str:
        """
        Generate SQL query for no_duplicates test (Snowflake-specific).

        Snowflake does NOT support GROUP BY *, so we must use explicit column names.
        If columns are not provided, we fetch them from the table.
        """
        # If columns provided, use them
        if columns and len(columns) > 0:
            column_list = ", ".join(columns)
            return f"""
                SELECT COUNT(*)
                FROM (
                    SELECT {column_list}, COUNT(*) as row_count
                    FROM {table_name}
                    GROUP BY {column_list}
                    HAVING COUNT(*) > 1
                ) AS duplicate_groups
            """

        # Snowflake doesn't support GROUP BY *, so we must get columns
        # Try to get columns from the table
        if not self.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        table_columns = self.get_table_columns(table_name)
        if not table_columns or len(table_columns) == 0:
            # If we can't get columns, raise an error with helpful message
            raise ValueError(
                f"Cannot generate no_duplicates test query for {table_name}: "
                "Unable to retrieve column names. Snowflake requires explicit column names for GROUP BY."
            )

        # Use the retrieved columns
        column_list = ", ".join(table_columns)
        return f"""
            SELECT COUNT(*)
            FROM (
                SELECT {column_list}, COUNT(*) as row_count
                FROM {table_name}
                GROUP BY {column_list}
                HAVING COUNT(*) > 1
            ) AS duplicate_groups
        """


# Register the adapter
register_adapter("snowflake", SnowflakeAdapter)
