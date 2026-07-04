"""
Python function file parsing functionality for UDFs.

Uses execution-based discovery: Python files are executed, and functions
auto-register themselves via @functions.sql(), @functions.python(), or SQLFunctionMetadata.
"""

import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any

from t4t.parser.shared.exceptions import FunctionParsingError
from t4t.parser.shared.registry import FunctionRegistry
from t4t.parser.shared.types import FilePath

from .base import BaseParser

# Configure logging
logger = logging.getLogger(__name__)


class FunctionPythonParsingError(FunctionParsingError):
    """Raised when Python function parsing fails."""

    pass


class FunctionPythonParser(BaseParser):
    """Handles Python file parsing and function extraction using execution-based discovery."""

    def __init__(self):
        """Initialize the Python function parser."""
        super().__init__()
        # Cache for evaluated functions (lazy evaluation)
        self._evaluation_cache: dict[str, Any] = {}

    def clear_cache(self) -> None:
        """Clear all caches."""
        super().clear_cache()
        self._evaluation_cache.clear()

    def parse(self, content: str, file_path: FilePath = None) -> dict[str, dict[str, Any]]:
        """
        Parse Python content and extract UDF functions using execution-based discovery.

        This method executes the Python file, which causes functions to auto-register
        themselves via @functions.sql(), @functions.python(), or SQLFunctionMetadata.

        Args:
            content: The Python content to parse
            file_path: Optional file path for context

        Returns:
            Dict mapping function_name to function registration data

        Raises:
            FunctionPythonParsingError: If parsing fails
        """
        if file_path is None:
            raise FunctionPythonParsingError("file_path is required for Python function parsing")

        file_path = Path(file_path)
        file_path_str = str(file_path)

        # Check cache first
        if file_path_str in self._cache:
            logger.debug(f"Using cached result for {file_path}")
            return self._cache[file_path_str]

        try:
            logger.debug(f"Parsing Python function file: {file_path}")

            # Execute the file to trigger auto-registration
            # Functions will register themselves via decorators or SQLFunctionMetadata
            self._execute_python_file(content, file_path)

            # Collect all functions registered from this file
            # Functions register themselves during execution, so we collect from registry
            all_functions = FunctionRegistry.get_all()
            functions = {}

            # Filter functions by file_path (functions registered from this file)
            # Use absolute paths for comparison
            file_path_abs = str(file_path.absolute())
            for function_name, function_data in all_functions.items():
                function_file_path = function_data.get("function_metadata", {}).get("file_path")
                # Compare absolute paths
                if function_file_path:
                    function_file_path_abs = str(Path(function_file_path).absolute())
                    if function_file_path_abs == file_path_abs:
                        functions[function_name] = function_data
                        logger.debug(f"Found function from {file_path}: {function_name}")

            # Cache the result
            self._set_cache(file_path_str, functions)
            if functions:
                logger.debug(
                    f"Successfully registered {len(functions)} function(s) from {file_path}"
                )
            return functions

        except Exception as e:
            if isinstance(e, FunctionPythonParsingError):
                raise
            raise FunctionPythonParsingError(
                f"Error parsing Python function file {file_path}: {str(e)}"
            ) from e

    def _execute_python_file(self, content: str, file_path: Path) -> None:
        """
        Execute a Python file in an isolated module namespace.

        The file will have access to: functions.sql, functions.python, SQLFunctionMetadata
        Functions will auto-register themselves when executed.

        Args:
            content: Python file content
            file_path: Path to the Python file

        Raises:
            FunctionPythonParsingError: If execution fails
        """
        module_name = f"temp_module_{hash(file_path)}"

        try:
            # Create a module spec and execute the file
            spec = importlib.util.spec_from_loader(module_name, loader=None)
            if spec is None:
                raise FunctionPythonParsingError(f"Could not create module spec for {file_path}")

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module

            # Inject function decorators and SQLFunctionMetadata into the module
            from t4t.typing import FunctionMetadata

            from ..processing.function_builder import SQLFunctionMetadata
            from ..processing.function_decorator import functions

            module.functions = functions
            module.SQLFunctionMetadata = SQLFunctionMetadata
            module.FunctionMetadata = FunctionMetadata

            # Also inject into tee.parser structure for imports
            if "tee" not in sys.modules:
                import types

                tee_module = types.ModuleType("tee")
                sys.modules["tee"] = tee_module
            if "tee.parser" not in sys.modules:
                import types

                parser_module = types.ModuleType("parser")
                sys.modules["tee.parser"] = parser_module
            if "tee.parser.processing" not in sys.modules:
                import types

                processing_module = types.ModuleType("processing")
                sys.modules["tee.parser.processing"] = processing_module
            # Ensure function_builder module exists and has SQLFunctionMetadata
            if not hasattr(sys.modules["tee.parser.processing"], "function_builder"):
                import types

                processing_module = sys.modules["tee.parser.processing"]
                processing_module.function_builder = types.ModuleType("function_builder")
                sys.modules["tee.parser.processing.function_builder"] = (
                    processing_module.function_builder
                )
            sys.modules[
                "tee.parser.processing.function_builder"
            ].SQLFunctionMetadata = SQLFunctionMetadata

            # Set __file__ to absolute path so functions can find companion files and match file_path
            file_path_abs = str(file_path.absolute())
            module.__file__ = file_path_abs

            # Inject a special variable that decorators can use to get the file path
            # This is more reliable than frame inspection in executed modules
            module.__tee_file_path__ = file_path_abs

            # Execute the file content
            # This will trigger auto-registration of functions via decorators or SQLFunctionMetadata
            exec(content, module.__dict__)

            logger.debug(f"Executed Python function file: {file_path}")

        except Exception as e:
            if isinstance(e, FunctionPythonParsingError):
                raise
            raise FunctionPythonParsingError(
                f"Failed to execute Python function file {file_path}: {e}"
            ) from e
        finally:
            # Clean up
            if module_name in sys.modules:
                del sys.modules[module_name]
