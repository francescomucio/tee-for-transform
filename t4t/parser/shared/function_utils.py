"""
Utility functions for function metadata standardization.
"""

import hashlib
from typing import Any

from t4t.typing.metadata import FunctionMetadata, FunctionParameter, FunctionType


def create_function_metadata(
    function_name: str,
    schema: str | None = None,
    file_path: str | None = None,
    description: str | None = None,
    function_type: FunctionType = "scalar",
    language: str | None = None,
    parameters: list[FunctionParameter] | None = None,
    return_type: str | None = None,
    metadata: FunctionMetadata | None = None,
) -> dict[str, Any]:
    """
    Create standardized function metadata.

    Args:
        function_name: Name of the function
        schema: Optional schema name
        file_path: Path to the source file
        description: Description of the function
        function_type: Function type (scalar, aggregate, table)
        language: Function language (sql, python, javascript)
        parameters: List of function parameters
        return_type: Return type for scalar/aggregate functions
        metadata: Additional metadata dictionary

    Returns:
        Standardized function metadata dictionary
    """
    # Prioritize file metadata description over parameter description
    final_description = description
    if metadata and metadata.get("description"):
        final_description = metadata.get("description")

    result: dict[str, Any] = {
        "function_name": function_name,
        "schema": schema,
        "description": final_description,
        "function_type": function_type,
        "language": language or "sql",
        "parameters": parameters or [],
        "return_type": return_type,
        "metadata": metadata or {},
    }

    # Add file_path if provided
    if file_path is not None:
        result["file_path"] = file_path

    return result


def standardize_parsed_function(
    function_data: dict[str, Any],
    function_name: str,
    file_path: str | None = None,
    is_python_function: bool = False,
) -> dict[str, Any]:
    """
    Standardize a parsed function to have consistent structure.

    Args:
        function_data: Current function data
        function_name: Name of the function
        file_path: Path to the source file
        is_python_function: Whether this is a Python function

    Returns:
        Standardized function data with code and function_metadata keys
    """
    # Extract existing metadata
    if is_python_function:
        # For Python functions, we need to get metadata from function_metadata
        original_metadata = function_data.get("function_metadata", {})
        function_metadata = original_metadata.copy()
    else:
        # For SQL functions, create metadata from parsed data
        original_metadata = function_data.get("function_metadata", {})
        function_metadata = original_metadata.copy()

    # Ensure required fields
    function_metadata.setdefault("function_name", function_name)
    function_metadata.setdefault("function_type", "scalar")
    function_metadata.setdefault("language", "sql")
    function_metadata.setdefault("parameters", [])
    function_metadata.setdefault("tags", [])
    function_metadata.setdefault("object_tags", {})
    function_metadata.setdefault("tests", [])

    # Keep code data
    code_data = function_data.get("code")

    # Compute hash of the function SQL for change detection
    function_hash = ""
    if code_data and "sql" in code_data:
        sql_content = code_data["sql"].get("original_sql", "")
        if sql_content:
            function_hash = hashlib.sha256(sql_content.encode("utf-8")).hexdigest()

    # Add file_path to function_metadata if provided (for consistent access)
    if file_path:
        function_metadata["file_path"] = file_path

    # Return standardized structure
    result = {
        "code": code_data,
        "function_metadata": function_metadata,
        "function_hash": function_hash,
    }

    # Preserve needs_evaluation flag (important for SQL-generating functions)
    # If not explicitly set, determine based on language
    needs_evaluation = function_data.get("needs_evaluation")
    if needs_evaluation is None:
        needs_evaluation = function_metadata.get("language") == "sql"
    result["needs_evaluation"] = needs_evaluation

    # Also store file_path at top level for backward compatibility
    if file_path:
        result["file_path"] = file_path

    return result


def validate_function_metadata_consistency(
    sql_metadata: dict[str, Any], python_metadata: dict[str, Any]
) -> None:
    """
    Validate that SQL and Python metadata are consistent.

    Args:
        sql_metadata: Metadata extracted from SQL
        python_metadata: Metadata from Python file

    Raises:
        FunctionMetadataError: If there are conflicts
    """
    from t4t.parser.shared.exceptions import FunctionMetadataError

    # Check function name consistency
    sql_name = sql_metadata.get("function_name")
    python_name = python_metadata.get("function_name")
    if sql_name and python_name and sql_name != python_name:
        raise FunctionMetadataError(
            f"Function name mismatch: SQL has '{sql_name}', Python has '{python_name}'"
        )

    # Check parameter consistency (if both have parameters)
    sql_params = sql_metadata.get("parameters", [])
    python_params = python_metadata.get("parameters", [])
    if sql_params and python_params:
        if len(sql_params) != len(python_params):
            raise FunctionMetadataError(
                f"Parameter count mismatch: SQL has {len(sql_params)}, Python has {len(python_params)}"
            )

        # Check parameter names match
        for i, (sql_param, python_param) in enumerate(zip(sql_params, python_params, strict=True)):
            if sql_param.get("name") != python_param.get("name"):
                raise FunctionMetadataError(
                    f"Parameter {i + 1} name mismatch: SQL has '{sql_param.get('name')}', "
                    f"Python has '{python_param.get('name')}'"
                )

    # Check return type consistency
    sql_return = sql_metadata.get("return_type")
    python_return = python_metadata.get("return_type")
    if sql_return and python_return and sql_return.upper() != python_return.upper():
        # This is a warning, not an error (types might be equivalent)
        logger = __import__("logging").getLogger(__name__)
        logger.warning(
            f"Return type mismatch: SQL has '{sql_return}', Python has '{python_return}'. "
            f"Using Python metadata."
        )
