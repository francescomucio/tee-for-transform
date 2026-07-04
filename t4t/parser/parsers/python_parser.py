"""
Python file parsing functionality for SQL models.

Uses execution-based discovery: Python files are executed, and models
auto-register themselves via @model decorator, create_model(), or SqlModelMetadata.
"""

import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any

import sqlglot

from t4t.parser.shared.exceptions import (
    ModelConflictError,
    PythonParsingError,
    SQLParsingError,
)
from t4t.parser.shared.model_utils import standardize_parsed_model
from t4t.parser.shared.registry import ModelRegistry
from t4t.parser.shared.types import FilePath, ParsedModel, Variables

from .base import BaseParser
from .sql_parser import SQLParser

# Configure logging
logger = logging.getLogger(__name__)


class PythonModelError(PythonParsingError):
    """Raised when Python model execution fails."""

    pass


class PythonParser(BaseParser):
    """Handles Python file parsing and model extraction using execution-based discovery."""

    def __init__(self):
        """Initialize the Python parser."""
        super().__init__()
        # Cache for evaluated functions (lazy evaluation)
        self._evaluation_cache: dict[str, Any] = {}
        # SQL parser for parsing SQLGlot expressions
        self._sql_parser = SQLParser()

    def clear_cache(self) -> None:
        """Clear all caches."""
        super().clear_cache()
        self._evaluation_cache.clear()
        logger.debug("Python parser caches cleared")

    def parse(self, content: str, file_path: FilePath = None) -> ParsedModel:
        """
        Parse Python content and extract SQL models using execution-based discovery.

        This method executes the Python file, which causes models to auto-register
        themselves via @model decorator, create_model(), or SqlModelMetadata.

        Args:
            content: The Python content to parse
            file_path: Optional file path for context

        Returns:
            Dict mapping table_name to model registration data

        Raises:
            PythonParsingError: If parsing fails
        """
        if file_path is None:
            raise PythonParsingError("file_path is required for Python parsing")

        file_path = Path(file_path)
        file_path_str = str(file_path)

        # Check cache first
        if file_path_str in self._cache:
            logger.debug(f"Using cached result for {file_path}")
            return self._cache[file_path_str]

        try:
            logger.debug(f"Parsing Python file: {file_path}")

            # Execute the file to trigger auto-registration
            # Models will register themselves via @model, create_model(), or SqlModelMetadata
            self._execute_python_file(content, file_path)

            # Collect all models registered from this file
            # Models register themselves during execution, so we collect from registry
            all_models = ModelRegistry.get_all()
            models = {}

            # Filter models by file_path (models registered from this file)
            # Use absolute paths for comparison
            file_path_abs = str(file_path.absolute())
            for table_name, model_data in all_models.items():
                model_file_path = model_data.get("model_metadata", {}).get("file_path")
                # Compare absolute paths
                if model_file_path:
                    model_file_path_abs = str(Path(model_file_path).absolute())
                    if model_file_path_abs == file_path_abs:
                        models[table_name] = model_data
                        logger.debug(f"Found model from {file_path}: {table_name}")

            # Cache the result
            self._set_cache(file_path_str, models)
            if models:
                logger.debug(f"Successfully registered {len(models)} models from {file_path}")
            return models

        except Exception as e:
            if isinstance(e, PythonParsingError):
                raise
            raise PythonParsingError(f"Error parsing Python file {file_path}: {str(e)}") from e

    def evaluate_model_function(
        self,
        model_data: dict[str, Any],
        full_table_name: str = None,
        variables: Variables | None = None,
    ) -> dict[str, Any]:
        """
        Evaluate a model function and return the SQL string.

        This method provides lazy evaluation of model functions when they are actually needed.

        Args:
            model_data: Model registration data from parse
            full_table_name: Full table name with schema (e.g., my_schema.users_summary)
            variables: Optional dictionary of variables to inject into the function's namespace

        Returns:
            Updated model data with parsed SQL
        """
        file_path = model_data["model_metadata"]["file_path"]
        function_name = model_data["model_metadata"]["function_name"]
        cache_key = f"{file_path}:{function_name}"

        # Check evaluation cache first
        if cache_key in self._evaluation_cache:
            logger.debug(f"Using cached evaluation result for {function_name}")
            return self._evaluation_cache[cache_key]

        try:
            logger.debug(f"Evaluating function {function_name} from {file_path}")

            # Evaluate the function to get the SQL string
            file_path_obj = Path(file_path)  # Convert string back to Path
            sql_string = self._execute_function(file_path_obj, function_name, variables)

            # Validate SQL syntax before proceeding
            try:
                parsed = sqlglot.parse_one(sql_string)
                if parsed is None:
                    raise PythonModelError(
                        f"Function {function_name} returned invalid SQL (parse returned None)"
                    )
            except Exception as e:
                raise PythonModelError(
                    f"Function {function_name} returned invalid SQL: {str(e)}"
                ) from e

            # Get table name for qualified SQL generation
            # Use full_table_name if provided (with schema), otherwise fall back to metadata table_name
            table_name = (
                full_table_name if full_table_name else model_data["model_metadata"]["table_name"]
            )

            # Parse the SQL string using the SQL parser
            parsed_data = self._sql_parser.parse(
                sql_string, file_path=file_path, table_name=table_name
            )

            # Update model data with code data while maintaining standardized structure
            updated_model_data = model_data.copy()
            updated_model_data["code"] = parsed_data["code"]
            updated_model_data["sqlglot_hash"] = parsed_data.get("sqlglot_hash", "")
            updated_model_data["needs_evaluation"] = False

            # Ensure the structure remains standardized
            updated_model_data = standardize_parsed_model(
                model_data=updated_model_data,
                table_name=full_table_name
                if full_table_name
                else model_data["model_metadata"]["table_name"],
                file_path=file_path,
                is_python_model=True,
            )

            # Cache the result
            self._evaluation_cache[cache_key] = updated_model_data
            logger.debug(
                f"Successfully evaluated model: {model_data['model_metadata']['table_name']}"
            )

            return updated_model_data

        except Exception as e:
            if isinstance(e, PythonModelError):
                raise
            raise PythonModelError(
                f"Error evaluating function {function_name} in {file_path}: {str(e)}"
            ) from e

    def evaluate_all_models(
        self, parsed_models: dict[str, Any], variables: Variables | None = None
    ) -> dict[str, Any]:
        """
        Evaluate all Python models that need evaluation.

        This method is called by the orchestrator to evaluate Python models before SQL execution.

        Args:
            parsed_models: Parsed models from parse
            variables: Optional dictionary of variables to inject into model functions

        Returns:
            Updated parsed models with parsed SQL
        """
        updated_models = parsed_models.copy()

        for table_name, model_data in parsed_models.items():
            if model_data.get("needs_evaluation", False):
                try:
                    # Pass the full table name (with schema) for qualified SQL generation
                    updated_models[table_name] = self.evaluate_model_function(
                        model_data, table_name, variables
                    )
                except Exception as e:
                    logger.error(f"Failed to evaluate model {table_name}: {e}")
                    # Keep the original model data but mark as failed
                    updated_models[table_name]["evaluation_error"] = str(e)
                    updated_models[table_name]["needs_evaluation"] = False

        return updated_models

    def update_models_with_resolved_sql(self, updated_models: dict[str, Any]) -> None:
        """
        Update the parser's cached models with resolved SQL from execution.

        This method should be called by the executor after execution to ensure
        the parser's cached models are updated with the resolved SQL.

        Args:
            updated_models: Models with resolved SQL from execution
        """
        for table_name, model_data in updated_models.items():
            # Skip None or invalid model data
            if not model_data or not isinstance(model_data, dict):
                continue

            # Only update Python models (those with function_name and file_path)
            code_data = model_data.get("code", {})
            if (
                "function_name" in model_data
                and "file_path" in model_data
                and code_data
                and "sql" in code_data
                and "resolved_sql" in code_data["sql"]
            ):
                # Update the execution cache with resolved SQL
                cache_key = f"{model_data['file_path']}:{model_data['function_name']}"
                if cache_key in self._execution_cache:
                    self._execution_cache[cache_key] = model_data
                    logger.debug(f"Updated execution cache with resolved SQL for {table_name}")

                # Also update the file cache if it exists
                file_path = model_data["file_path"]
                if file_path in self._cache and table_name in self._cache[file_path]:
                    self._cache[file_path][table_name] = model_data
                    logger.debug(f"Updated file cache with qualified SQL for {table_name}")

    def _execute_function(
        self, file_path: Path, function_name: str, variables: Variables | None = None
    ) -> str:
        """
        Execute a function from a Python file and return its result.

        Args:
            file_path: Path to the Python file
            function_name: Name of the function to execute
            variables: Optional dictionary of variables to inject into the function's namespace

        Returns:
            SQL string returned by the function

        Raises:
            PythonModelError: If function execution fails or returns invalid type
        """
        from t4t.parser.shared.registry import FunctionRegistry, ModelRegistry

        module_name = f"temp_module_{hash(file_path)}_{function_name}"

        # Set flag to skip registration during evaluation
        # This prevents decorators from re-registering models when we're just executing functions
        ModelRegistry.set_skip_registration(True)
        FunctionRegistry.set_skip_registration(True)

        try:
            # Create a module spec
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None or spec.loader is None:
                raise PythonModelError(f"Could not load module from {file_path}")

            # Create and load the module
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module

            # Inject the model decorator and factory before loading the module
            from ..processing.model import create_model, model

            module.model = model
            module.create_model = create_model

            # Also inject it into the tee.parser module structure
            if "tee" not in sys.modules:
                import types

                tee_module = types.ModuleType("tee")
                sys.modules["tee"] = tee_module
            if "tee.parser" not in sys.modules:
                import types

                parser_module = types.ModuleType("parser")
                sys.modules["tee.parser"] = parser_module
            if "tee.parser.model" not in sys.modules:
                import types

                model_module = types.ModuleType("model")
                model_module.model = model
                model_module.create_model = create_model
                sys.modules["tee.parser.model"] = model_module

            # Set __file__ and __tee_file_path__ before executing module
            # This ensures decorators can find the correct file path
            file_path_abs = str(file_path.absolute())
            module.__file__ = file_path_abs
            module.__tee_file_path__ = file_path_abs

            spec.loader.exec_module(module)

            # Inject variables into the module's namespace if provided
            if variables:
                for var_name, var_value in variables.items():
                    setattr(module, var_name, var_value)
                logger.debug(
                    f"Injected variables {list(variables.keys())} into module {module_name}"
                )

            # Inject the model decorator and factory to make them available
            from ..processing.model import create_model, model

            module.model = model
            module.create_model = create_model
            logger.debug(f"Injected model decorator and create_model into module {module_name}")

            # Get the function
            if not hasattr(module, function_name):
                raise PythonModelError(f"Function {function_name} not found in {file_path}")

            func = getattr(module, function_name)

            # Execute the function
            logger.debug(f"Executing function {function_name} from {file_path}")
            result = func()

            # Validate result is a string
            if not isinstance(result, str):
                raise PythonModelError(
                    f"Function {function_name} must return a SQL string, got {type(result)}. "
                    f"If using sqlglot, convert to string: return str(exp.select(...))"
                )

            # Validate SQL string is not empty
            if not result or not result.strip():
                raise PythonModelError(f"Function {function_name} returned an empty SQL string")

            return result.strip()

        except Exception as e:
            if isinstance(e, PythonModelError):
                raise
            raise PythonModelError(
                f"Error executing function {function_name} in {file_path}: {str(e)}"
            ) from e
        finally:
            # Always reset the flag, even if an error occurred
            ModelRegistry.set_skip_registration(False)
            FunctionRegistry.set_skip_registration(False)

    def _execute_python_file(self, content: str, file_path: Path) -> None:
        """
        Execute a Python file in an isolated module namespace.

        The file will have access to: model, create_model, SqlModelMetadata
        Models will auto-register themselves when executed.

        Args:
            content: Python file content
            file_path: Path to the Python file

        Raises:
            PythonParsingError: If execution fails
        """
        module_name = f"temp_module_{hash(file_path)}"

        try:
            # Create a module spec and execute the file
            spec = importlib.util.spec_from_loader(module_name, loader=None)
            if spec is None:
                raise PythonParsingError(f"Could not create module spec for {file_path}")

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module

            # Inject model decorator, create_model, and SqlModelMetadata into the module
            from t4t.typing import ModelMetadata

            from ..processing.model import create_model, model
            from ..processing.model_builder import SqlModelMetadata

            module.model = model
            module.create_model = create_model
            module.SqlModelMetadata = SqlModelMetadata
            module.ModelMetadata = ModelMetadata

            # Also inject into tee.parser structure for imports
            if "tee" not in sys.modules:
                import types

                tee_module = types.ModuleType("tee")
                sys.modules["tee"] = tee_module
            if "tee.parser" not in sys.modules:
                import types

                parser_module = types.ModuleType("parser")
                sys.modules["tee.parser"] = parser_module
            # Inject tee.parser.model for backward compatibility
            if "tee.parser.model" not in sys.modules:
                import types

                model_module = types.ModuleType("model")
                model_module.model = model
                model_module.create_model = create_model
                sys.modules["tee.parser.model"] = model_module
            if "tee.parser.processing" not in sys.modules:
                import types

                processing_module = types.ModuleType("processing")
                sys.modules["tee.parser.processing"] = processing_module
            # Ensure model_builder module exists and has SqlModelMetadata
            if not hasattr(sys.modules["tee.parser.processing"], "model_builder"):
                import types

                processing_module = sys.modules["tee.parser.processing"]
                processing_module.model_builder = types.ModuleType("model_builder")
                sys.modules["tee.parser.processing.model_builder"] = processing_module.model_builder
            sys.modules["tee.parser.processing.model_builder"].SqlModelMetadata = SqlModelMetadata

            # Set __file__ to absolute path so models can find companion files and match file_path
            file_path_abs = str(file_path.absolute())
            module.__file__ = file_path_abs

            # Inject a special variable that decorators can use to get the file path
            # This is more reliable than frame inspection in executed modules
            module.__tee_file_path__ = file_path_abs

            # Execute the file content
            # This will trigger auto-registration of models via decorators/factory functions
            exec(content, module.__dict__)

            # Auto-magically detect and instantiate SqlModelMetadata if metadata exists
            # This makes it easier for users - they just need to define metadata
            if "metadata" in module.__dict__:
                metadata_value = module.__dict__["metadata"]
                # Check if metadata is a dict (ModelMetadata is a TypedDict, which is a dict)
                if isinstance(metadata_value, dict):
                    # Check if there's a companion .sql file
                    sql_file_path = file_path.with_suffix(".sql")
                    if sql_file_path.exists():
                        # Check if a model was already registered from this file
                        # (to avoid double registration if user explicitly instantiated SqlModelMetadata)
                        file_path_abs = str(file_path.absolute())
                        # Use efficient existence check that stops at first match
                        if not ModelRegistry.has_models_from_file(file_path_abs):
                            try:
                                logger.debug(f"Auto-instantiating SqlModelMetadata for {file_path}")
                                # Create SqlModelMetadata instance using __new__() to bypass normal __init__
                                # This is necessary because:
                                # 1. Frame inspection (get_caller_file_and_main) doesn't work when called
                                #    from within _execute_python_file due to the execution context
                                # 2. We need to manually set _caller_file before __post_init__ runs
                                # 3. __post_init__ checks if _caller_file is already set and skips
                                #    frame inspection if it is, allowing our manual value to be used
                                instance = SqlModelMetadata.__new__(SqlModelMetadata)
                                instance.metadata = metadata_value
                                instance._caller_file = file_path_abs
                                instance._caller_main = False
                                # Now call __post_init__ manually to trigger model creation
                                instance.__post_init__()
                                # If for some reason the model wasn't created, log a warning
                                if not instance.model:
                                    logger.warning(
                                        f"Auto-instantiated SqlModelMetadata for {file_path} but model was not created"
                                    )
                            except ModelConflictError as e:
                                # Model conflict is a real problem - log as warning so user knows
                                logger.warning(
                                    f"Model conflict detected during auto-instantiation for {file_path}: {e}"
                                )
                            except SQLParsingError as e:
                                # SQL parsing error indicates invalid SQL - log as warning so user knows
                                logger.warning(
                                    f"SQL parsing error during auto-instantiation for {file_path}: {e}"
                                )
                            except Exception as e:
                                # Other errors - log as debug (expected in some cases, e.g., user might
                                # have intentionally not instantiated it or there might be other issues)
                                logger.debug(
                                    f"Auto-instantiation of SqlModelMetadata failed for {file_path}: {e}"
                                )

            logger.debug(f"Executed Python file: {file_path}")

        except Exception as e:
            if isinstance(e, PythonParsingError):
                raise
            raise PythonParsingError(f"Failed to execute Python file {file_path}: {e}") from e
        finally:
            # Clean up
            if module_name in sys.modules:
                del sys.modules[module_name]
