"""
Utility for building Model instances from metadata and SQL files.
"""

import os

from tee.parser.parsers.sql_parser import SQLParser
from tee.typing import Model, ModelMetadata


def build_model_from_file(
    metadata: ModelMetadata,
    file_path: str | None = None,
    sql_file_path: str | None = None,
    table_name: str | None = None,
) -> Model | None:
    """
    Build a Model instance from metadata and a corresponding SQL file.

    Args:
        metadata: ModelMetadata dictionary
        file_path: Path to the Python file (used to find the SQL file if sql_file_path not provided).
                   This path is also stored in the model metadata so that PythonParser can match
                   the model to its source file during discovery.
        sql_file_path: Optional explicit path to the SQL file
        table_name: Optional explicit table name (defaults to filename without extension)

    Returns:
        Model instance or None if SQL file not found
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

    with open(sql_file_path) as f:
        sql_content = f.read()

    if not sql_content:
        return None

    # Determine table name
    if table_name is None:
        table_name = os.path.splitext(os.path.basename(file_path))[0]

    # Get description from metadata
    description = None
    if isinstance(metadata, dict):
        description = metadata.get("description", None)

    # Use SQL parser to properly parse the SQL content
    # This extracts operation_type, source_tables, source_functions, etc.
    sql_parser = SQLParser()
    parsed_sql = sql_parser.parse(sql_content, file_path=sql_file_path, table_name=table_name)

    # Combine parsed SQL with metadata
    # The SQL parser already provides the code structure with proper SQL analysis
    model: Model = {
        "code": parsed_sql.get("code"),
        "model_metadata": {
            "table_name": table_name,
            "function_name": None,
            "description": description,
            "variables": [],
            "metadata": metadata,
            "file_path": file_path,  # Required: PythonParser uses this to match models to source files
        },
        "sqlglot_hash": parsed_sql.get("sqlglot_hash", ""),
    }

    return model


def build_and_print_model(metadata: ModelMetadata, file_path: str | None = None) -> Model | None:
    """
    Build and print a model from metadata and SQL file.

    This is a convenience function that combines build_model_from_file and printing.
    It automatically detects the SQL file based on the Python file path.

    Args:
        metadata: ModelMetadata dictionary
        file_path: Optional path to the Python file (auto-detected from caller if not provided)

    Returns:
        Model instance or None if SQL file not found
    """
    # Auto-detect file_path from caller if not provided
    if file_path is None:
        import inspect

        frame = inspect.currentframe()
        if frame and frame.f_back:
            file_path = frame.f_back.f_globals.get("__file__")
            if file_path:
                file_path = os.path.abspath(file_path)

    model = build_model_from_file(metadata, file_path=file_path)

    if model:
        print("\nModel object (created directly using Model type):")
        print(model)
    else:
        print("\nSQL file not found, model not created.")

    return model


def auto_build_model(metadata: ModelMetadata) -> Model | None:
    """
    Automatically build and print a model when the script is run as main.

    This function checks if it's being called from __main__ and only executes then.
    Call this at module level (not inside if __name__ == "__main__") and it will
    automatically handle the __main__ check internally.

    Args:
        metadata: ModelMetadata dictionary

    Returns:
        Model instance or None if not in __main__ context or SQL file not found

    Example:
        from tee.parser.shared.model_builder import auto_build_model
        from tee.typing import ModelMetadata

        metadata: ModelMetadata = {...}
        auto_build_model(metadata)  # Only runs when script is executed directly
    """
    import inspect

    # Check if we're being called from __main__ context
    frame = inspect.currentframe()
    if frame and frame.f_back:
        caller_globals = frame.f_back.f_globals
        if caller_globals.get("__name__") != "__main__":
            return None

    # If we're in __main__, build and print the model
    return build_and_print_model(metadata)
