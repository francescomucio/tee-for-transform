"""
Table name resolution and generation functionality.
"""

from pathlib import Path
from typing import Any

from t4t.parser.shared.exceptions import TableResolutionError
from t4t.parser.shared.types import ConnectionConfig, ParsedFunction, ParsedModel


class TableResolver:
    """Handles table name generation and resolution based on connection type."""

    def __init__(self, connection: ConnectionConfig) -> None:
        """
        Initialize the TableResolver.

        Args:
            connection: Connection configuration dict with 'type' key
        """
        self.connection = connection

    def generate_full_table_name(self, sql_file: Path, models_folder: Path) -> str:
        """
        Generate the full table name based on the connection type and file path.

        Args:
            sql_file: Path to the SQL file
            models_folder: Path to the models folder

        Returns:
            Full table name string

        Raises:
            TableResolutionError: If table name generation fails
        """
        try:
            # Handle both dict and AdapterConfig
            connection_type = (
                self.connection.get("type")
                if hasattr(self.connection, "get")
                else self.connection.type
            )
            if connection_type == "duckdb":
                # For DuckDB: first parent folder in models + "." + file_name_without_sql
                relative_path = sql_file.relative_to(models_folder)
                path_parts = relative_path.parts

                if len(path_parts) >= 2:
                    # First parent folder (schema) + file name without extension
                    schema_name = path_parts[0]
                    file_name = sql_file.stem  # filename without .sql extension
                    return f"{schema_name}.{file_name}"
                else:
                    # If file is directly in models folder
                    return sql_file.stem
            else:
                # For other connection types, use file path but remove all extensions
                relative_path = sql_file.relative_to(models_folder)
                # Convert path separators to dots and remove all file extensions
                table_name = str(relative_path).replace("/", ".").replace("\\", ".")
                # Remove any file extension (not just .sql)
                if "." in table_name:
                    table_name = table_name.rsplit(".", 1)[0]
                return table_name
        except Exception as e:
            raise TableResolutionError(f"Failed to generate table name for {sql_file}: {e}") from e

    def resolve_table_reference(
        self, table_ref: str, parsed_models: dict[str, ParsedModel]
    ) -> str | None:
        """
        Resolve a table reference to its full table name.

        Args:
            table_ref: The referenced table name
            parsed_models: Parsed models dict

        Returns:
            Full table name if found, None otherwise
        """
        # Direct match
        if table_ref in parsed_models:
            return table_ref

        # Try to find by partial name (without schema)
        table_name_only = table_ref.split(".")[-1]
        for full_name in parsed_models:
            if full_name.split(".")[-1] == table_name_only:
                return full_name

        return None

    def generate_full_function_name(
        self, function_file: Path, functions_folder: Path, function_metadata: dict[str, Any]
    ) -> str:
        """
        Generate the full function name based on the connection type, file path, and metadata.

        Args:
            function_file: Path to the function file
            functions_folder: Path to the functions folder
            function_metadata: Function metadata dictionary (may contain schema)

        Returns:
            Full function name string (schema.function_name)

        Raises:
            TableResolutionError: If function name generation fails
        """
        try:
            # Check if schema is specified in metadata
            schema = function_metadata.get("schema")
            function_name = function_metadata.get("function_name")

            if not function_name:
                raise TableResolutionError(
                    f"Function metadata missing 'function_name' for {function_file}"
                )

            # If schema is in metadata, use it
            if schema:
                return f"{schema}.{function_name}"

            # Otherwise, extract schema from file path (similar to tables)
            # Handle both dict and AdapterConfig
            connection_type = (
                self.connection.get("type")
                if hasattr(self.connection, "get")
                else self.connection.type
            )

            if connection_type == "duckdb":
                # For DuckDB: first parent folder in functions + "." + function_name
                relative_path = function_file.relative_to(functions_folder)
                path_parts = relative_path.parts

                if len(path_parts) >= 2:
                    # First parent folder (schema) + function name
                    schema_name = path_parts[0]
                    return f"{schema_name}.{function_name}"
                else:
                    # If file is directly in functions folder, use function name only
                    return function_name
            else:
                # For other connection types, use file path structure
                relative_path = function_file.relative_to(functions_folder)
                path_parts = relative_path.parts

                if len(path_parts) >= 2:
                    # First parent folder (schema) + function name
                    schema_name = path_parts[0]
                    return f"{schema_name}.{function_name}"
                else:
                    # If file is directly in functions folder, use function name only
                    return function_name

        except Exception as e:
            raise TableResolutionError(
                f"Failed to generate function name for {function_file}: {e}"
            ) from e

    def resolve_function_reference(
        self, function_ref: str, parsed_functions: dict[str, ParsedFunction]
    ) -> str | None:
        """
        Resolve a function reference to its full function name.

        Args:
            function_ref: The referenced function name
            parsed_functions: Parsed functions dict

        Returns:
            Full function name if found, None otherwise
        """
        # Direct match
        if function_ref in parsed_functions:
            return function_ref

        # Try to find by partial name (without schema)
        function_name_only = function_ref.split(".")[-1]
        for full_name in parsed_functions:
            if full_name.split(".")[-1] == function_name_only:
                return full_name

        return None
