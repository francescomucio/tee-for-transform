"""
Function decorators for Python-based UDF definitions.
Inspired by the model decorator pattern.
"""

import inspect
import logging
import os
from collections.abc import Callable
from typing import Any

from tee.parser.shared.exceptions import ParserError
from tee.parser.shared.function_utils import standardize_parsed_function
from tee.parser.shared.inspect_utils import get_caller_file_info
from tee.parser.shared.registry import FunctionRegistry
from tee.typing.metadata import FunctionParameter, FunctionType

# Configure logging
logger = logging.getLogger(__name__)


class FunctionDecoratorError(ParserError):
    """Raised when function decorator validation fails."""

    pass


def sql(
    function_name: str | None = None,
    description: str | None = None,
    function_type: FunctionType | None = None,
    parameters: list[FunctionParameter] | None = None,
    return_type: str | None = None,
    return_table_schema: list[dict[str, Any]] | None = None,
    schema: str | None = None,
    deterministic: bool | None = None,
    database_name: str | None = None,
    tags: list[str] | None = None,
    object_tags: dict[str, str] | None = None,
    **metadata: Any,
) -> Callable:
    """
    Decorator for marking Python functions as SQL-generating UDFs.

    This decorator stores metadata on the function. The function should return
    SQL code (as a string) or a dict mapping adapter types to SQL code.

    Args:
        function_name: Optional custom function name. If not provided, uses function name.
        description: Optional description of the function.
        function_type: Function type ("scalar", "aggregate", "table"). Default: "scalar".
        parameters: Optional list of function parameters.
        return_type: Optional return type (for scalar/aggregate functions).
        return_table_schema: Optional table schema (for table functions).
        schema: Optional schema name.
        deterministic: Whether the function is deterministic.
        database_name: Optional database-specific name (for overloading).
        tags: Optional list of tags (dbt-style).
        object_tags: Optional dict of object tags (database-style).
        **metadata: Additional metadata to store with the function.

    Returns:
        Decorated function with function metadata stored as _function_metadata attribute.

    Example:
        @functions.sql(
            function_name="calculate_metric",
            return_type="FLOAT",
            tags=["analytics"]
        )
        def generate_calc_sql(adapter_type: str) -> str:
            if adapter_type == "snowflake":
                return "CREATE FUNCTION ..."
            return "CREATE FUNCTION ..."
    """

    def decorator(func: Callable) -> Callable:
        try:
            # Validate function name
            if not func.__name__ or not func.__name__.replace("_", "").isalnum():
                raise FunctionDecoratorError(f"Invalid function name: {func.__name__}")

            # Validate function name parameter
            final_function_name = function_name or func.__name__
            if not final_function_name.replace(".", "").replace("_", "").isalnum():
                raise FunctionDecoratorError(f"Invalid function name: {final_function_name}")

            # Get caller file path for registration
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
                )  # decorator -> sql() -> @functions.sql() -> module

            # Ensure absolute path
            if caller_file:
                caller_file = os.path.abspath(caller_file)

            # Extract docstring if description not provided
            final_description = description
            if not final_description and func.__doc__:
                final_description = func.__doc__.strip()

            # Create function metadata dict
            function_metadata_dict = {
                "function_name": final_function_name,
                "description": final_description,
                "function_type": function_type or "scalar",
                "language": "sql",
                "parameters": parameters or [],
                "return_type": return_type,
                "return_table_schema": return_table_schema,
                "schema": schema,
                "deterministic": deterministic,
                "database_name": database_name,
                "tags": tags or [],
                "object_tags": object_tags or {},
                "metadata": metadata,
            }

            # Store metadata on function (for backward compatibility)
            func._function_metadata = {
                **function_metadata_dict,
                "needs_evaluation": True,  # Flag indicating this function needs to be evaluated
            }

            # Create function data structure
            function_data = {
                "function_metadata": {
                    **function_metadata_dict,
                    "file_path": caller_file,
                },
                "needs_evaluation": True,  # SQL-generating functions need evaluation
                "code": None,  # Will be populated when evaluated
            }

            # Standardize and register the function
            standardized_function = standardize_parsed_function(
                function_data=function_data,
                function_name=final_function_name,
                file_path=caller_file,
                is_python_function=False,  # SQL-generating function
            )

            # Check for conflicts (only if from a different file)
            existing_function = FunctionRegistry.get(final_function_name)
            if existing_function:
                existing_file = existing_function.get("function_metadata", {}).get("file_path")
                # Normalize paths for comparison
                if existing_file and caller_file:
                    existing_file_abs = os.path.abspath(existing_file)
                    caller_file_abs = os.path.abspath(caller_file)
                    if existing_file_abs != caller_file_abs:
                        raise FunctionDecoratorError(
                            f"Function name conflict: '{final_function_name}' is already registered from another file. "
                            f"Use explicit 'function_name' parameter to avoid conflicts."
                        )
                elif existing_file:  # existing_file exists but caller_file doesn't
                    raise FunctionDecoratorError(
                        f"Function name conflict: '{final_function_name}' is already registered from another file. "
                        f"Use explicit 'function_name' parameter to avoid conflicts."
                    )

            FunctionRegistry.register(standardized_function)
            logger.debug(
                f"Registered function: {final_function_name} from function {func.__name__}"
            )

            return func

        except Exception as e:
            if isinstance(e, FunctionDecoratorError):
                raise
            raise FunctionDecoratorError(
                f"Failed to create SQL function decorator: {str(e)}"
            ) from e

    return decorator


def python(
    function_name: str | None = None,
    description: str | None = None,
    function_type: FunctionType | None = None,
    parameters: list[FunctionParameter] | None = None,
    return_type: str | None = None,
    return_table_schema: list[dict[str, Any]] | None = None,
    schema: str | None = None,
    deterministic: bool | None = None,
    database_name: str | None = None,
    tags: list[str] | None = None,
    object_tags: dict[str, str] | None = None,
    **metadata: Any,
) -> Callable:
    """
    Decorator for marking Python functions as Python UDFs.

    This decorator stores metadata on the function. The function will be executed
    as a Python UDF in the database (e.g., DuckDB Python UDFs).

    Args:
        function_name: Optional custom function name. If not provided, uses function name.
        description: Optional description of the function.
        function_type: Function type ("scalar", "aggregate", "table"). Default: "scalar".
        parameters: Optional list of function parameters.
        return_type: Optional return type (for scalar/aggregate functions).
        return_table_schema: Optional table schema (for table functions).
        schema: Optional schema name.
        deterministic: Whether the function is deterministic.
        database_name: Optional database-specific name (for overloading).
        tags: Optional list of tags (dbt-style).
        object_tags: Optional dict of object tags (database-style).
        **metadata: Additional metadata to store with the function.

    Returns:
        Decorated function with function metadata stored as _function_metadata attribute.

    Example:
        @functions.python(
            function_name="python_calculator",
            return_type="FLOAT",
            tags=["math"]
        )
        def python_calculator(x: float) -> float:
            return x * 2.5 + 10
    """

    def decorator(func: Callable) -> Callable:
        try:
            # Validate function name
            if not func.__name__ or not func.__name__.replace("_", "").isalnum():
                raise FunctionDecoratorError(f"Invalid function name: {func.__name__}")

            # Validate function name parameter
            final_function_name = function_name or func.__name__
            if not final_function_name.replace(".", "").replace("_", "").isalnum():
                raise FunctionDecoratorError(f"Invalid function name: {final_function_name}")

            # Get caller file path for registration
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
                )  # decorator -> python() -> @functions.python() -> module

            # Ensure absolute path
            if caller_file:
                caller_file = os.path.abspath(caller_file)

            # Extract docstring if description not provided
            final_description = description
            if not final_description and func.__doc__:
                final_description = func.__doc__.strip()

            # Create function metadata dict
            function_metadata_dict = {
                "function_name": final_function_name,
                "description": final_description,
                "function_type": function_type or "scalar",
                "language": "python",
                "parameters": parameters or [],
                "return_type": return_type,
                "return_table_schema": return_table_schema,
                "schema": schema,
                "deterministic": deterministic,
                "database_name": database_name,
                "tags": tags or [],
                "object_tags": object_tags or {},
                "metadata": metadata,
            }

            # Store metadata on function (for backward compatibility)
            func._function_metadata = {
                **function_metadata_dict,
                "needs_evaluation": False,  # Python UDFs don't need evaluation (they are the code)
            }

            # Create function data structure
            function_data = {
                "function_metadata": {
                    **function_metadata_dict,
                    "file_path": caller_file,
                },
                "needs_evaluation": False,
                "code": None,  # Python UDFs don't have SQL code
            }

            # Standardize and register the function
            standardized_function = standardize_parsed_function(
                function_data=function_data,
                function_name=final_function_name,
                file_path=caller_file,
                is_python_function=True,  # Python UDF
            )

            # Check for conflicts (only if from a different file)
            existing_function = FunctionRegistry.get(final_function_name)
            if existing_function:
                existing_file = existing_function.get("function_metadata", {}).get("file_path")
                # Normalize paths for comparison
                if existing_file and caller_file:
                    existing_file_abs = os.path.abspath(existing_file)
                    caller_file_abs = os.path.abspath(caller_file)
                    if existing_file_abs != caller_file_abs:
                        raise FunctionDecoratorError(
                            f"Function name conflict: '{final_function_name}' is already registered from another file. "
                            f"Use explicit 'function_name' parameter to avoid conflicts."
                        )
                elif existing_file:  # existing_file exists but caller_file doesn't
                    raise FunctionDecoratorError(
                        f"Function name conflict: '{final_function_name}' is already registered from another file. "
                        f"Use explicit 'function_name' parameter to avoid conflicts."
                    )

            FunctionRegistry.register(standardized_function)
            logger.debug(
                f"Registered function: {final_function_name} from function {func.__name__}"
            )

            return func

        except Exception as e:
            if isinstance(e, FunctionDecoratorError):
                raise
            raise FunctionDecoratorError(
                f"Failed to create Python function decorator: {str(e)}"
            ) from e

    return decorator


# Create a namespace class for easier imports
class functions:
    """Namespace for function decorators."""

    sql = sql
    python = python
