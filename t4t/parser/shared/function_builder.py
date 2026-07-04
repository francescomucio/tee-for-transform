"""
Utility for building Function instances from metadata and SQL files.
"""

import hashlib
import os
from typing import Any

from t4t.parser.parsers.function_sql_parser import FunctionSQLParser
from t4t.typing import Function, FunctionMetadata


def build_function_from_file(
    metadata: FunctionMetadata,
    file_path: str | None = None,
    sql_file_path: str | None = None,
    function_name: str | None = None,
    connection: dict[str, Any] | None = None,
    project_config: dict[str, Any] | None = None,
) -> Function | None:
    """
    Build a Function instance from metadata and a corresponding SQL file.

    Args:
        metadata: FunctionMetadata dictionary
        file_path: Path to the Python file (used to find the SQL file if sql_file_path not provided)
        sql_file_path: Optional explicit path to the SQL file
        function_name: Optional explicit function name (defaults to metadata function_name or filename)
        connection: Optional connection configuration for dialect inference
        project_config: Optional project configuration for dialect inference

    Returns:
        Function instance or None if SQL file not found
    """
    # Determine file paths
    if file_path is None:
        # Try to get from calling frame
        from .inspect_utils import get_caller_file_path

        file_path = get_caller_file_path(frames_up=2)

    if not file_path:
        return None

    # Find SQL file
    if sql_file_path is None:
        sql_file_path = os.path.splitext(file_path)[0] + ".sql"

    # Read SQL content
    if not os.path.exists(sql_file_path):
        return None

    with open(sql_file_path, encoding="utf-8") as f:
        sql_content = f.read()

    if not sql_content:
        return None

    # Determine function name
    if function_name is None:
        function_name = metadata.get("function_name")
        if not function_name:
            function_name = os.path.splitext(os.path.basename(file_path))[0]

    # Get description from metadata
    description = metadata.get("description", None)

    # Use FunctionSQLParser to properly parse the SQL content
    # This extracts function_name, parameters, return_type, dependencies, etc.
    function_parser = FunctionSQLParser(connection=connection, project_config=project_config)
    parsed_functions = function_parser.parse(sql_content, file_path=sql_file_path)

    # Get the parsed function (should be one function per file)
    if not parsed_functions or function_name not in parsed_functions:
        # Try to get the first (and likely only) function
        if parsed_functions:
            function_name = list(parsed_functions.keys())[0]
        else:
            return None

    parsed_function_data = parsed_functions[function_name]

    # Extract parsed metadata and code
    parsed_metadata = parsed_function_data.get("function_metadata", {})
    parsed_code = parsed_function_data.get("code", {})

    # Merge metadata: user-provided metadata takes precedence
    function_type = metadata.get("function_type") or parsed_metadata.get("function_type", "scalar")
    language = metadata.get("language") or parsed_metadata.get("language", "sql")
    parameters = metadata.get("parameters") or parsed_metadata.get("parameters", [])
    return_type = metadata.get("return_type") or parsed_metadata.get("return_type")
    return_table_schema = metadata.get("return_table_schema") or parsed_metadata.get(
        "return_table_schema"
    )
    schema = metadata.get("schema") or parsed_metadata.get("schema")
    deterministic = metadata.get("deterministic")
    if deterministic is None:
        deterministic = parsed_metadata.get("deterministic", False)
    tests = metadata.get("tests") or parsed_metadata.get("tests", [])
    tags = metadata.get("tags") or parsed_metadata.get("tags", [])
    object_tags = metadata.get("object_tags") or parsed_metadata.get("object_tags", {})

    # Build function_metadata structure
    function_metadata_info = {
        "function_name": function_name,
        "description": description,
        "function_type": function_type,
        "language": language,
        "parameters": parameters or [],
        "return_type": return_type,
        "return_table_schema": return_table_schema,
        "schema": schema,
        "deterministic": deterministic,
        "tests": tests or [],
        "tags": tags or [],
        "object_tags": object_tags or {},
        "metadata": metadata,
    }

    # Add file_path to function_metadata if provided (for consistent access)
    if file_path:
        function_metadata_info["file_path"] = file_path

    # Build code structure
    sql_data = parsed_code.get("sql", {})
    function_code = None
    if sql_data:
        function_code = {
            "sql": {
                "original_sql": sql_data.get("original_sql", sql_content),
                # Don't set resolved_sql here - it will be set after conversion in the executor
                # This ensures conversion always happens, even if the SQL is already in the target dialect
                "operation_type": "create_function",  # Functions are CREATE statements
                "source_tables": sql_data.get("source_tables", []),
                "source_functions": sql_data.get("source_functions", []),
                "dialect": sql_data.get("dialect"),  # Preserve dialect from parser for conversion
            }
        }

    # Compute hash
    function_hash = hashlib.sha256(sql_content.encode("utf-8")).hexdigest()

    # Determine if function needs evaluation
    # SQL-generating functions need evaluation, Python UDFs don't
    needs_evaluation = language == "sql"

    # Combine into Function structure
    function: Function = {
        "code": function_code,
        "function_metadata": function_metadata_info,
        "function_hash": function_hash,
        "needs_evaluation": needs_evaluation,
        "file_path": file_path,
    }

    return function
