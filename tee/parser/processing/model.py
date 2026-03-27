"""
Model creation utilities for Python-based SQL models.

This module provides both decorator and factory patterns for creating models:
- @model decorator: For decorating functions as models
- create_model(): For programmatically creating models

Inspired by dlt's resource decorator pattern.
"""

import inspect
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tee.parser.parsers.sql_parser import SQLParser
from tee.parser.shared.exceptions import ParserError
from tee.parser.shared.inspect_utils import get_caller_file_info
from tee.parser.shared.model_utils import standardize_parsed_model
from tee.parser.shared.registry import ModelRegistry

# Configure logging
logger = logging.getLogger(__name__)


class ModelError(ParserError):
    """Base exception for model-related errors."""

    pass


class ModelDecoratorError(ModelError):
    """Raised when model decorator validation fails."""

    pass


class ModelFactoryError(ModelError):
    """Raised when model factory operations fail."""

    pass


def create_model_metadata(
    table_name: str,
    function_name: str | None = None,
    description: str | None = None,
    variables: list[str] | None = None,
    needs_evaluation: bool = True,
    sql: str | None = None,
    **metadata: Any,
) -> dict[str, Any]:
    """
    Create standardized model metadata dictionary.

    This is a shared utility used by both the decorator and factory functions.

    Args:
        table_name: Name of the table/model
        function_name: Optional function name (defaults to table_name)
        description: Optional description
        variables: Optional list of variable names
        needs_evaluation: Whether the model needs evaluation
        sql: Optional SQL string (for pre-computed models)
        **metadata: Additional metadata

    Returns:
        Dictionary with model metadata
    """
    return {
        "table_name": table_name,
        "function_name": function_name or table_name,
        "description": description,
        "variables": variables or [],
        "metadata": metadata,
        "needs_evaluation": needs_evaluation,
        "sql": sql,  # Store SQL if provided
    }


def model(
    table_name: str | None = None,
    description: str | None = None,
    variables: list[str] | None = None,
    **metadata: Any,
) -> Callable:
    """
    Decorator for marking Python functions as SQL models.

    This decorator follows the dlt pattern - it stores metadata on the function
    without executing it. The function is only executed when actually needed.

    Args:
        table_name: Optional custom table name. If not provided, uses function name.
        description: Optional description of the model.
        variables: Optional list of variable names to inject into the function's namespace.
        **metadata: Additional metadata to store with the model.

    Returns:
        Decorated function with model metadata stored as _model_metadata attribute.

    Example:
        @model(table_name="custom_table", description="My custom table", variables=["env", "debug"])
        def my_function():
            return f"SELECT * FROM other_table WHERE environment = '{env}'"

        # If using sqlglot, convert to string:
        # from sqlglot import exp
        # return str(exp.select("*").from_("other_table").where(exp.column("environment") == env))
    """

    def decorator(func: Callable) -> Callable:
        try:
            # Validate function name
            if not func.__name__ or not func.__name__.replace("_", "").isalnum():
                raise ModelDecoratorError(f"Invalid function name: {func.__name__}")

            # Validate table name
            final_table_name = table_name or func.__name__
            if (
                final_table_name
                and not final_table_name.replace(".", "").replace("_", "").isalnum()
            ):
                raise ModelDecoratorError(f"Invalid table name: {final_table_name}")

            # Get caller file path for registration
            # First try to get from __tee_file_path__ (injected by parser for executed modules)
            # Otherwise fall back to frame inspection
            import os

            frame = inspect.currentframe()
            caller_file = None

            # Walk up the frame stack to find the module's __tee_file_path__ or __file__
            current_frame = frame
            for _ in range(5):  # Go up to 5 frames to find the module
                if current_frame and current_frame.f_back:
                    current_frame = current_frame.f_back
                    frame_globals = current_frame.f_globals
                    # Check for __tee_file_path__ first (most reliable)
                    if "__tee_file_path__" in frame_globals:
                        caller_file = frame_globals["__tee_file_path__"]
                        break
                    # Fall back to __file__
                    if "__file__" in frame_globals:
                        caller_file = frame_globals["__file__"]
                        # Don't break here - keep looking for __tee_file_path__ in higher frames
                else:
                    break

            # If still not found, use get_caller_file_info
            if not caller_file:
                caller_file, _ = get_caller_file_info(
                    frames_up=3
                )  # decorator -> model() -> @model -> module

            # Ensure absolute path
            if caller_file:
                caller_file = os.path.abspath(caller_file)

            # Create metadata using shared utility
            # Note: create_model_metadata in model_utils has different signature
            # We'll create the metadata dict directly here
            model_metadata_dict = {
                "table_name": final_table_name,
                "function_name": func.__name__,
                "description": description,
                "variables": variables or [],
                "metadata": metadata,
            }

            # Store metadata on function (for backward compatibility)
            func._model_metadata = model_metadata_dict

            # Create model data structure
            model_data = {
                "model_metadata": {
                    **model_metadata_dict,
                    "file_path": caller_file,
                },
                "needs_evaluation": True,
                "code": None,  # Will be populated when evaluated
            }

            # Standardize and register the model
            standardized_model = standardize_parsed_model(
                model_data=model_data,
                table_name=final_table_name,
                file_path=caller_file,
                is_python_model=True,
            )

            # Skip registration if we're in evaluation mode
            if ModelRegistry.should_skip_registration():
                logger.debug(f"Skipping registration of {final_table_name} (evaluation mode)")
                return func

            # Check for conflicts (only if from a different file)
            # Allow re-registration from the same file (e.g., when evaluating functions)
            existing_model = ModelRegistry.get(final_table_name)
            if existing_model:
                existing_file = existing_model.get("model_metadata", {}).get("file_path")
                # Normalize paths for comparison
                if existing_file and caller_file:
                    existing_file_abs = os.path.abspath(existing_file)
                    caller_file_abs = os.path.abspath(caller_file)
                    if existing_file_abs != caller_file_abs:
                        raise ModelDecoratorError(
                            f"Model name conflict: '{final_table_name}' is already registered from another file. "
                            f"Use explicit 'table_name' parameter to avoid conflicts."
                        )
                elif existing_file:  # existing_file exists but caller_file doesn't
                    raise ModelDecoratorError(
                        f"Model name conflict: '{final_table_name}' is already registered from another file. "
                        f"Use explicit 'table_name' parameter to avoid conflicts."
                    )

            ModelRegistry.register(standardized_model)
            logger.debug(f"Registered model: {final_table_name} from function {func.__name__}")

            return func

        except Exception as e:
            if isinstance(e, ModelDecoratorError):
                raise
            raise ModelDecoratorError(f"Failed to create model decorator: {str(e)}") from e

    return decorator


def create_model(
    table_name: str,
    sql: str | None = None,
    description: str | None = None,
    variables: list[str] | None = None,
    **metadata: Any,
) -> None:
    """
    Dynamically create and register a model without using a decorator.

    This function registers the model with ModelRegistry when called.
    It's designed for programmatic model creation, e.g., within loops.

    Args:
        table_name: Name of the table/model to create
        sql: SQL query string (required)
        description: Optional description of the model
        variables: Optional list of variable names to inject
        **metadata: Additional metadata to store with the model

    Example:
        from tee.parser.model import create_model

        for table in ["users", "orders"]:
            create_model(
                table_name=table,
                sql=f"SELECT * FROM staging.{table}",
                description=f"Select from staging.{table}"
            )

    Raises:
        ModelFactoryError: If validation fails or sql is missing
    """
    # Validate inputs
    if not sql:
        raise ModelFactoryError("sql parameter is required for create_model()")

    # Validate table name
    if not table_name or not table_name.replace(".", "").replace("_", "").isalnum():
        raise ModelFactoryError(f"Invalid table name: {table_name}")

    # Skip registration early if we're in evaluation/metadata parsing mode
    # This prevents unnecessary work and avoids conflicts
    if ModelRegistry.should_skip_registration():
        logger.debug(f"Skipping registration of {table_name} via create_model() (evaluation mode)")
        return

    # Get caller file path
    # First try to get from __tee_file_path__ (injected by parser for executed modules)
    # Otherwise fall back to frame inspection
    frame = inspect.currentframe()
    caller_file = None

    # Walk up the frame stack to find the module's __tee_file_path__ or __file__
    current_frame = frame
    for _ in range(4):  # Go up to 4 frames to find the module
        if current_frame and current_frame.f_back:
            current_frame = current_frame.f_back
            frame_globals = current_frame.f_globals
            # Check for __tee_file_path__ first (most reliable)
            if "__tee_file_path__" in frame_globals:
                caller_file = frame_globals["__tee_file_path__"]
                break
            # Fall back to __file__
            if "__file__" in frame_globals:
                caller_file = frame_globals["__file__"]
                # Don't break here - keep looking for __tee_file_path__ in higher frames
        else:
            break

    # If still not found, use get_caller_file_info
    if not caller_file:
        caller_file, _ = get_caller_file_info(frames_up=2)  # create_model() -> module

    # Ensure absolute path
    if caller_file:
        caller_file = os.path.abspath(caller_file)

    # Create metadata dict
    model_metadata_dict = {
        "table_name": table_name,
        "function_name": f"create_{table_name}".replace(".", "_"),
        "description": description,
        "variables": variables or [],
        "metadata": metadata,
    }

    # Derive schema from file path (same logic as TableResolver.generate_full_table_name)
    # This is needed to qualify table references in the SQL
    full_table_name_for_qualification = table_name
    if caller_file:
        try:
            caller_path = Path(caller_file)
            # Try to find models folder by looking for project structure
            # For now, assume schema is the parent folder name if file is in a subfolder
            if caller_path.parent.name and caller_path.parent.name != "models":
                # Parent folder is likely the schema (e.g., my_schema/)
                schema_name = caller_path.parent.name
                # Only add schema if table_name doesn't already have one
                if "." not in table_name:
                    full_table_name_for_qualification = f"{schema_name}.{table_name}"
        except Exception as e:
            logger.debug(f"Could not derive schema from file path {caller_file}: {e}")

    # Parse SQL through SQLParser to get qualified SQL (same as @model does)
    # This ensures table references are qualified with schema prefixes
    # Pass full_table_name_with_schema so generate_resolved_sql can use the schema
    # Use caller_file if available, otherwise use a temporary path for parsing
    sql_parser = SQLParser()
    parse_file_path = caller_file if caller_file else None
    parsed_sql_data = sql_parser.parse(
        sql, file_path=parse_file_path, table_name=full_table_name_for_qualification
    )

    # Extract code data from parsed result (contains qualified resolved_sql)
    # SQLParser.parse() returns a single model dict with "code" key
    if parsed_sql_data and "code" in parsed_sql_data:
        code_data = parsed_sql_data["code"]
    else:
        # Fallback if parsing fails (shouldn't happen, but be safe)
        logger.warning(
            f"SQL parsing returned invalid result for {table_name}, using unqualified SQL"
        )
        code_data = {
            "sql": {
                "original_sql": sql,
                "resolved_sql": sql,
                "operation_type": "select",
                "source_tables": [],
                "source_functions": [],
            }
        }

    # Create model data structure
    model_data = {
        "model_metadata": {
            **model_metadata_dict,
            "file_path": caller_file,
        },
        "code": code_data,
        "needs_evaluation": False,
    }

    # Standardize and register the model
    standardized_model = standardize_parsed_model(
        model_data=model_data,
        table_name=table_name,
        file_path=caller_file,
        is_python_model=False,  # SQL is provided directly, not from function
    )

    # Check for conflicts (only if from a different file)
    # Allow re-registration from the same file (e.g., when file is executed multiple times)
    existing_model = ModelRegistry.get(table_name)
    if existing_model:
        existing_file = existing_model.get("model_metadata", {}).get("file_path")
        # Normalize paths for comparison
        if existing_file and caller_file:
            existing_file_abs = os.path.abspath(existing_file)
            caller_file_abs = os.path.abspath(caller_file)
            if existing_file_abs != caller_file_abs:
                raise ModelFactoryError(
                    f"Model name conflict: '{table_name}' is already registered from another file. "
                    f"Use a different table_name to avoid conflicts."
                )
        elif existing_file:  # existing_file exists but caller_file doesn't
            raise ModelFactoryError(
                f"Model name conflict: '{table_name}' is already registered from another file. "
                f"Use a different table_name to avoid conflicts."
            )
        # If both are None or paths match, allow re-registration (same file)

    ModelRegistry.register(standardized_model)
    logger.debug(f"Registered model via create_model(): {table_name}")
