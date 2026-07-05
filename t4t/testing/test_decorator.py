"""
Test decorator and factory function for creating tests programmatically in Python files.

Supports @test decorator and create_test() function for defining tests in Python.
"""

import inspect
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .base import TestRegistry, TestSeverity
from .python_test import PythonTest

logger = logging.getLogger(__name__)


class TestDecoratorError(Exception):
    """Raised when test decorator operations fail."""

    __test__ = False  # Tell pytest this is not a test class

    pass


def _derive_test_name(file_path: str | None, function_name: str | None = None) -> str:
    """
    Derive test name from file path and function name.

    Format: {folder_name}__{file_name}__{function_name}
    If in root tests/ folder: {file_name}__{function_name}

    Args:
        file_path: Path to the Python test file
        function_name: Name of the function (if from decorator)

    Returns:
        Derived test name
    """
    if not file_path:
        if not function_name:
            raise TestDecoratorError(
                "Cannot derive test name: both file_path and function_name are None"
            )
        return function_name

    path = Path(file_path)
    file_stem = path.stem  # filename without extension

    # Get folder name (relative to tests/ folder)
    # If path is: tests/my_schema/check_minimum_rows.py
    # parts = ['tests', 'my_schema', 'check_minimum_rows.py']
    parts = path.parts
    if len(parts) > 1 and parts[-2] != "tests":
        # Has subfolder: use subfolder name
        folder_name = parts[-2]
        if function_name:
            return f"{folder_name}__{file_stem}__{function_name}"
        return f"{folder_name}__{file_stem}"
    else:
        # In root tests/ folder
        if function_name:
            return f"{file_stem}__{function_name}"
        return file_stem


def test(
    name: str | None = None,
    severity: str | TestSeverity = "error",
    description: str | None = None,
    tags: list[str] | None = None,
    **_metadata: Any,
) -> Callable:
    """
    Decorator for marking Python functions as SQL tests.

    When the function is defined, it registers a test with TestRegistry.
    The function should return a SQL query string.

    Args:
        name: Optional test name. If not provided, uses {folder_name}__{file_name}__{function_name}
        severity: Test severity level ("error" or "warning"). Default: "error"
        description: Optional test description
        tags: Optional list of tags
        **_metadata: Additional metadata (reserved for future use on PythonTest)

    Returns:
        Decorated function (unchanged, test is registered on definition)

    Example:
        @test(name="check_minimum_rows", severity="error")
        def check_minimum_rows():
            return '''
            SELECT 1 as violation
            FROM @table_name
            GROUP BY 1
            HAVING COUNT(*) < @min_rows:10
            '''
    """
    # Convert severity string to enum if needed
    if isinstance(severity, str):
        severity_enum = TestSeverity.ERROR if severity.lower() == "error" else TestSeverity.WARNING
    else:
        severity_enum = severity

    def decorator(func: Callable) -> Callable:
        try:
            # Get caller's file path
            frame = inspect.currentframe()
            caller_file = None
            if frame and frame.f_back:
                caller_globals = frame.f_back.f_globals
                caller_file = caller_globals.get("__file__")

            # Derive test name if not provided
            test_name = name
            if not test_name:
                test_name = _derive_test_name(caller_file, func.__name__)

            # Validate test name
            if not test_name or not test_name.replace("_", "").replace(".", "").isalnum():
                raise TestDecoratorError(f"Invalid test name: {test_name}")

            # Execute function to get SQL (at registration time)
            # This allows the function to use variables, f-strings, etc.
            try:
                sql = func()
                if not isinstance(sql, str):
                    raise TestDecoratorError(
                        f"Test function {func.__name__} must return a SQL string, got {type(sql)}"
                    )
                if not sql.strip():
                    raise TestDecoratorError(
                        f"Test function {func.__name__} returned an empty SQL string"
                    )
            except Exception as e:
                raise TestDecoratorError(
                    f"Failed to execute test function {func.__name__} to get SQL: {e}"
                ) from e

            # Create and register test
            python_test = PythonTest(
                name=test_name,
                sql=sql.strip(),
                severity=severity_enum,
                description=description,
                tags=tags or [],
            )

            # Check for conflicts
            existing_test = TestRegistry.get(test_name)
            if existing_test:
                raise TestDecoratorError(
                    f"Test name conflict: '{test_name}' is already registered from another file. "
                    f"Use explicit 'name' parameter to avoid conflicts."
                )

            TestRegistry.register(python_test)
            logger.debug(f"Registered test: {test_name} from function {func.__name__}")

            return func

        except Exception as e:
            if isinstance(e, TestDecoratorError):
                raise
            raise TestDecoratorError(f"Failed to create test decorator: {str(e)}") from e

    return decorator


# Tell pytest this is not a test function (it's a decorator)
test.__test__ = False


def create_test(
    name: str,
    sql: str,
    severity: str | TestSeverity = "error",
    description: str | None = None,
    tags: list[str] | None = None,
    **_metadata: Any,
) -> None:
    """
    Dynamically create a test without using a decorator.

    This function registers a test with TestRegistry when called.
    Useful for creating tests programmatically (e.g., in loops).

    Args:
        name: Test name (required)
        sql: SQL query string (required)
        severity: Test severity level ("error" or "warning"). Default: "error"
        description: Optional test description
        tags: Optional list of tags
        **_metadata: Additional metadata (reserved for future use on PythonTest)

    Raises:
        TestDecoratorError: If validation fails or name conflicts

    Example:
        from t4t.testing import create_test

        for table in ["users", "orders"]:
            create_test(
                name=f"check_{table}_not_empty",
                sql=f"SELECT 1 FROM {table} WHERE COUNT(*) = 0",
                severity="error"
            )
    """
    try:
        # Validate inputs
        if not name:
            raise TestDecoratorError("name parameter is required for create_test()")

        if not sql or not sql.strip():
            raise TestDecoratorError(
                "sql parameter is required and cannot be empty for create_test()"
            )

        # Validate test name
        if not name.replace("_", "").replace(".", "").isalnum():
            raise TestDecoratorError(f"Invalid test name: {name}")

        # Convert severity string to enum if needed
        if isinstance(severity, str):
            severity_enum = (
                TestSeverity.ERROR if severity.lower() == "error" else TestSeverity.WARNING
            )
        else:
            severity_enum = severity

        # Check for conflicts
        existing_test = TestRegistry.get(name)
        if existing_test:
            raise TestDecoratorError(
                f"Test name conflict: '{name}' is already registered from another file. "
                f"Use a different name to avoid conflicts."
            )

        # Create and register test
        python_test = PythonTest(
            name=name,
            sql=sql.strip(),
            severity=severity_enum,
            description=description,
            tags=tags or [],
        )

        TestRegistry.register(python_test)
        logger.debug(f"Registered test via create_test(): {name}")

    except Exception as e:
        if isinstance(e, TestDecoratorError):
            raise
        raise TestDecoratorError(f"Failed to create test: {str(e)}") from e
