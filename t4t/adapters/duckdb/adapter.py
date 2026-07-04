"""
DuckDB adapter with SQLglot integration.

This adapter provides DuckDB-specific functionality including:
- SQL dialect conversion
- DuckDB-specific optimizations
- Connection management
- Materialization support
- MotherDuck cloud database support
"""

import os
from typing import Any

try:
    import duckdb
except ImportError:
    duckdb = None

from t4t.adapters.base import AdapterConfig, DatabaseAdapter, MaterializationType
from t4t.adapters.registry import register_adapter

from .functions.function_manager import FunctionManager
from .materialization.incremental_handler import IncrementalHandler
from .materialization.table_handler import TableHandler
from .materialization.view_handler import ViewHandler
from .utils.helpers import DuckDBUtils


class DuckDBAdapter(DatabaseAdapter):
    """DuckDB and MotherDuck database adapter with SQLglot integration."""

    def __init__(self, config: AdapterConfig) -> None:
        if duckdb is None:
            raise ImportError("DuckDB is not installed. Install it with: uv add duckdb")

        super().__init__(config)

        # Initialize component managers
        self.function_manager = FunctionManager(self)
        self.table_handler = TableHandler(self)
        self.view_handler = ViewHandler(self)
        self.incremental_handler = IncrementalHandler(self)
        self.utils = DuckDBUtils(self)

    def get_default_dialect(self) -> str:
        """Get the default SQL dialect for DuckDB."""
        return "duckdb"

    def get_supported_materializations(self) -> list[MaterializationType]:
        """Get list of supported materialization types for DuckDB."""
        return [
            MaterializationType.TABLE,
            MaterializationType.VIEW,
            MaterializationType.INCREMENTAL,
        ]

    def _extract_motherduck_path(self, db_path: str) -> str:
        """
        Extract MotherDuck path from potentially resolved absolute path.

        Args:
            db_path: Database path (may be "md:db" or "/path/to/md:db")

        Returns:
            Clean MotherDuck path (e.g., "md:db") or original path if not MotherDuck
        """
        # Check if this is a MotherDuck connection
        is_motherduck = (
            db_path.startswith("md:")
            or db_path.startswith("motherduck:")
            or "/md:" in db_path
            or "/motherduck:" in db_path
        )

        if not is_motherduck:
            return db_path

        # Extract the md:database_name part if path was resolved to absolute
        if "/" in db_path and ("md:" in db_path or "motherduck:" in db_path):
            # Path was resolved, extract the md: part
            parts = db_path.split("/")
            md_part = next(
                (p for p in parts if p.startswith("md:") or p.startswith("motherduck:")), None
            )
            if md_part:
                return md_part

        return db_path

    def _is_motherduck_path(self, db_path: str) -> bool:
        """Check if path indicates a MotherDuck connection."""
        return (
            db_path.startswith("md:")
            or db_path.startswith("motherduck:")
            or "/md:" in db_path
            or "/motherduck:" in db_path
        )

    def connect(self) -> None:
        """Establish connection to DuckDB database or MotherDuck."""
        db_path = self.config.path or ":memory:"
        db_path = self._extract_motherduck_path(db_path)

        # Check if this is a MotherDuck connection
        if self._is_motherduck_path(db_path):
            # Extract database name from path (e.g., "md:my_db" -> "my_db")
            # Remove prefix and query parameters
            clean_path = db_path.split("?")[0]
            db_name = clean_path.split(":", 1)[1] if ":" in clean_path else None

            # Build connection string to MotherDuck service (without database name)
            service_connection_string = self._build_motherduck_connection_string("md:")

            # Try to connect to MotherDuck service first
            # If it fails, try to install the extension
            try:
                self.connection = duckdb.connect(service_connection_string)
            except Exception as e:
                error_msg = str(e).lower()
                original_error = str(e)

                # Check if this is an extension-related error
                is_extension_error = any(
                    keyword in error_msg for keyword in ["motherduck", "extension", "init", "load"]
                )

                if is_extension_error:
                    # Try to install the extension in a temporary connection
                    self.logger.info("Attempting to install MotherDuck extension...")
                    try:
                        temp_conn = duckdb.connect(":memory:")
                        try:
                            temp_conn.execute("INSTALL motherduck;")
                            self.logger.debug("MotherDuck extension installation command executed")
                        except Exception as install_cmd_error:
                            # Extension might already be installed, or installation might have failed
                            self.logger.debug(f"INSTALL command result: {install_cmd_error}")
                        temp_conn.close()

                        # Try connecting again - DuckDB should auto-load it now
                        self.connection = duckdb.connect(service_connection_string)
                        self.logger.info("MotherDuck extension installed and connection successful")
                    except Exception as retry_error:
                        # Connection still failed after installation attempt
                        error_details = str(retry_error)
                        raise RuntimeError(
                            f"Could not connect to MotherDuck after extension installation attempt.\n"
                            f"Original error: {original_error}\n"
                            f"Retry error: {error_details}\n\n"
                            "The extension may need to be installed manually. Try:\n"
                            '  duckdb -c "INSTALL motherduck;"\n'
                            "  python -c \"import duckdb; conn = duckdb.connect(); conn.execute('INSTALL motherduck;')\"\n\n"
                            "If the extension is already installed, check:\n"
                            "  - Your MOTHERDUCK_TOKEN is valid\n"
                            "  - Network connectivity to MotherDuck"
                        ) from retry_error
                else:
                    # Not an extension error, re-raise the original exception
                    raise

            # If a database name was specified, create it if needed and use it
            if db_name:
                try:
                    # Create database if it doesn't exist
                    self.connection.execute(f"CREATE DATABASE IF NOT EXISTS {db_name};")
                    # Switch to the database
                    self.connection.execute(f"USE {db_name};")
                    self.logger.info(f"Connected to MotherDuck database: {db_name}")
                except Exception as db_error:
                    # If database operations fail, try alternative: attach to the database
                    try:
                        # Try attaching which might work if database exists
                        attach_conn_string = self._build_motherduck_connection_string(
                            f"md:{db_name}"
                        )
                        # Close current connection and try direct connection
                        self.connection.close()
                        self.connection = duckdb.connect(attach_conn_string)
                        self.logger.info(
                            f"Connected to MotherDuck database: {db_name} (via attach)"
                        )
                    except Exception as attach_error:
                        raise RuntimeError(
                            f"Could not create or attach to MotherDuck database '{db_name}'.\n"
                            f"CREATE/USE error: {db_error}\n"
                            f"ATTACH error: {attach_error}\n\n"
                            "Please ensure:\n"
                            "  - Your MOTHERDUCK_TOKEN is valid\n"
                            "  - You have permissions to create databases\n"
                            "  - Network connectivity to MotherDuck"
                        ) from attach_error
            else:
                # No database specified, just connected to MotherDuck service
                self.logger.info("Connected to MotherDuck service")
        else:
            self.connection = duckdb.connect(db_path)
            self.logger.info(f"Connected to DuckDB database: {db_path}")

    def disconnect(self) -> None:
        """Close the DuckDB or MotherDuck connection."""
        if self.connection:
            self.connection.close()
            self.connection = None
            db_path = self.config.path or ":memory:"
            db_path = self._extract_motherduck_path(db_path)

            if self._is_motherduck_path(db_path):
                safe_path = db_path.split("?")[0] if "?" in db_path else db_path
                self.logger.info(f"Disconnected from MotherDuck database: {safe_path}")
            else:
                self.logger.info(f"Disconnected from DuckDB database: {db_path}")

    def execute_query(self, query: str) -> Any:
        """Execute a SQL query and return results."""
        if not self.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        try:
            result = self.connection.execute(query).fetchall()
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
        """Check if a table exists in the database."""
        if not self.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        try:
            # Handle schema-qualified table names (e.g., "my_schema.dim_brand")
            if "." in table_name:
                schema_name, table_name_only = table_name.split(".", 1)
                result = self.connection.execute(
                    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = ? AND table_name = ?",
                    [schema_name, table_name_only],
                ).fetchone()
            else:
                # No schema specified, check in default schema
                result = self.connection.execute(
                    "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
                    [table_name],
                ).fetchone()
            return result[0] > 0 if result else False
        except Exception:
            return False

    def drop_table(self, table_name: str) -> None:
        """Drop a table from the database."""
        if not self.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        try:
            self.utils.execute_query(f"DROP TABLE IF EXISTS {table_name}")
            self.logger.info(f"Dropped table: {table_name}")
        except Exception as e:
            self.logger.error(f"Error dropping table {table_name}: {e}")
            raise

    def get_table_info(self, table_name: str) -> dict[str, Any]:
        """Get information about a table."""
        if not self.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        try:
            # Get table schema
            schema_query = f"DESCRIBE {table_name}"
            schema_result = self.connection.execute(schema_query).fetchall()

            # Get row count
            count_query = f"SELECT COUNT(*) FROM {table_name}"
            count_result = self.connection.execute(count_query).fetchone()

            return {
                "schema": [{"column": row[0], "type": row[1]} for row in schema_result],
                "row_count": count_result[0] if count_result else 0,
            }
        except Exception as e:
            self.logger.error(f"Error getting table info for {table_name}: {e}")
            raise

    def describe_query_schema(self, sql_query: str) -> list[dict[str, Any]]:
        """Infer schema from SQL query output using DuckDB DESCRIBE."""
        if not self.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        try:
            # DuckDB supports DESCRIBE on queries
            describe_query = f"DESCRIBE SELECT * FROM ({sql_query}) LIMIT 0"
            result = self.connection.execute(describe_query).fetchall()

            # Convert to standard format: [{"name": "...", "type": "..."}]
            schema = []
            for row in result:
                schema.append({"name": row[0], "type": row[1]})

            return schema
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
            ddl = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
            self.utils.execute_query(ddl)
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
            self.utils.execute_query(ddl)
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
        self.function_manager.create(function_name, function_sql, metadata)

    def function_exists(self, function_name: str, signature: str | None = None) -> bool:
        """Check if a function exists in the database."""
        return self.function_manager.exists(function_name, signature)

    def drop_function(self, function_name: str) -> None:
        """Drop a function from the database."""
        self.function_manager.drop(function_name)

    def get_database_info(self) -> dict[str, Any]:
        """Get DuckDB or MotherDuck database information."""
        base_info = super().get_database_info()

        if self.connection:
            try:
                # Get DuckDB version
                version_result = self.connection.execute("SELECT version()").fetchone()
                base_info["duckdb_version"] = version_result[0] if version_result else "unknown"

                # Get database path or connection info
                db_path = self.config.path or ":memory:"
                if db_path.startswith("md:") or db_path.startswith("motherduck:"):
                    # For MotherDuck, show connection info without token
                    safe_path = db_path.split("?")[0] if "?" in db_path else db_path
                    base_info["database_path"] = safe_path
                    base_info["connection_type"] = "motherduck"
                else:
                    base_info["database_path"] = db_path
                    base_info["connection_type"] = "duckdb"

            except Exception as e:
                self.logger.warning(f"Could not get database-specific info: {e}")

        return base_info

    def get_table_columns(self, table_name: str) -> list[str]:
        """Get column names for a table."""
        if not self.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        try:
            # Use DESCRIBE to get column information
            result = self.connection.execute(f"DESCRIBE {table_name}").fetchall()
            return [row[0] for row in result]  # First column is the column name
        except Exception as e:
            self.logger.error(f"Error getting columns for table {table_name}: {e}")
            # Fallback to a default set of columns
            return ["id", "name", "created_at", "updated_at", "status"]

    def execute_incremental_append(self, table_name: str, sql_query: str) -> None:
        """Execute incremental append operation."""
        self.incremental_handler.execute_append(table_name, sql_query)

    def execute_incremental_merge(
        self, table_name: str, source_sql: str, config: dict[str, Any]
    ) -> None:
        """Execute incremental merge operation."""
        self.incremental_handler.execute_merge(table_name, source_sql, config)

    def execute_incremental_delete_insert(
        self, table_name: str, delete_sql: str, insert_sql: str
    ) -> None:
        """Execute incremental delete+insert operation."""
        self.incremental_handler.execute_delete_insert(table_name, delete_sql, insert_sql)

    def _generate_merge_sql(
        self, table_name: str, source_sql: str, unique_key: list[str], columns: list[str]
    ) -> str:
        """Generate DuckDB-specific MERGE SQL statement."""
        return self.incremental_handler._generate_merge_sql(
            table_name, source_sql, unique_key, columns
        )

    def generate_no_duplicates_test_query(
        self, table_name: str, columns: list[str] | None = None
    ) -> str:
        """
        Generate SQL query for no_duplicates test (DuckDB-specific).

        DuckDB supports GROUP BY * which makes this efficient.
        """
        if columns and len(columns) > 0:
            # Use provided columns
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

        # DuckDB supports GROUP BY * for grouping by all columns
        return f"""
            SELECT COUNT(*)
            FROM (
                SELECT *, COUNT(*) as row_count
                FROM {table_name}
                GROUP BY *
                HAVING COUNT(*) > 1
            ) AS duplicate_groups
        """

    def _build_motherduck_connection_string(self, db_path: str) -> str:
        """
        Build MotherDuck connection string with authentication token.

        Token can be provided via:
        1. Environment variable MOTHERDUCK_TOKEN (preferred)
        2. Config extra dict with key 'motherduck_token'
        3. Already in the connection string

        Args:
            db_path: MotherDuck connection string (e.g., "md:database_name")

        Returns:
            Complete connection string with token if needed
        """
        # Check if token is already in the connection string
        if "motherduck_token=" in db_path or "token=" in db_path:
            return db_path

        # Try to get token from environment variable (preferred method)
        token = os.getenv("MOTHERDUCK_TOKEN")

        # Fall back to config extra dict
        if not token and self.config.extra:
            token = self.config.extra.get("motherduck_token")

        # Build connection string (check for both None and empty string)
        if token and token.strip():
            # Add token as query parameter
            separator = "?" if "?" not in db_path else "&"
            return f"{db_path}{separator}motherduck_token={token}"

        # No token found - DuckDB will try to use default authentication
        # (e.g., from ~/.motherduck/config or other default locations)
        self.logger.warning(
            "No MotherDuck token found. Trying default authentication. "
            "Set MOTHERDUCK_TOKEN environment variable or add 'motherduck_token' to config.extra"
        )
        return db_path


# Register the adapter
register_adapter("duckdb", DuckDBAdapter)
