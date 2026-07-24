"""
Enhanced execution engine with pluggable database adapters.

This module provides the main execution engine that uses the new adapter system
for database-agnostic SQL model execution with automatic dialect conversion.
"""

import logging
from typing import Any

from t4t.adapters import AdapterConfig, get_adapter
from t4t.parser.shared.types import ParsedFunction

from .config import load_database_config
from .executors import FunctionExecutor, ModelExecutor
from .materialization import MaterializationHandler
from .metadata import MetadataExtractor
from .state import StateChecker

# Configure logging
logger = logging.getLogger(__name__)


class ExecutionEngine:
    """
    Enhanced execution engine with pluggable database adapters.

    This engine supports:
    - Automatic SQL dialect conversion using SQLglot
    - Pluggable database adapters
    - Configuration management from pyproject.toml and environment variables
    - Database-specific optimizations and features
    """

    def __init__(
        self,
        config: AdapterConfig | dict[str, Any] | None = None,
        config_name: str = "default",
        project_folder: str = ".",
        variables: dict[str, Any] | None = None,
        env_name: str | None = None,
        run_id: str | None = None,
    ) -> None:
        """
        Initialize the execution engine.

        Args:
            config: Database adapter configuration (AdapterConfig or dict, if None, loads from config files)
            config_name: Configuration name to load (if config is None)
            project_folder: Project folder path for state management
            variables: Optional dictionary of variables for model execution
            env_name: Environment name for scoping state
            run_id: Identity of the run, threaded into `ModelExecutor`
                (executors package) so model_started/model_finished events
                carry it.
        """
        self.config = config or load_database_config(config_name)
        self.adapter = get_adapter(self.config)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.project_folder = project_folder
        self.variables = variables or {}
        self.env_name = env_name
        self.run_id = run_id

        # Initialize components
        self.state_checker = StateChecker(project_folder, env_name=env_name)
        self.metadata_extractor = MetadataExtractor()
        self.materialization_handler = MaterializationHandler(
            self.adapter, self.state_checker.state_manager, self.variables
        )
        self.model_executor = ModelExecutor(
            self.adapter,
            project_folder,
            self.variables,
            self.materialization_handler,
            self.metadata_extractor,
            self.state_checker,
            self.config,
            run_id=self.run_id,
        )
        self.function_executor = FunctionExecutor(
            self.adapter, project_folder, self.metadata_extractor
        )

    def connect(self) -> None:
        """Establish connection to the database."""
        self.adapter.connect()

    def disconnect(self) -> None:
        """Close the database connection."""
        self.adapter.disconnect()
        self.state_checker.close()

    def execute_models(
        self, parsed_models: dict[str, Any], execution_order: list[str]
    ) -> dict[str, Any]:
        """
        Execute SQL models in the specified order with dialect conversion.

        Args:
            parsed_models: Dictionary mapping table names to parsed SQL arguments
            execution_order: List of table names in execution order

        Returns:
            Dictionary with execution results and status
        """
        return self.model_executor.execute(parsed_models, execution_order)

    def execute_functions(
        self, parsed_functions: dict[str, ParsedFunction], execution_order: list[str]
    ) -> dict[str, Any]:
        """
        Execute user-defined functions in dependency order.

        Functions are always created/overwritten (no versioning).
        Execution order should include functions before models that depend on them.

        Args:
            parsed_functions: Dictionary mapping function names to parsed function data
            execution_order: List of all objects (functions and models) in execution order

        Returns:
            Dictionary with execution results and status
        """
        return self.function_executor.execute(parsed_functions, execution_order)

    def get_database_info(self) -> dict[str, Any]:
        """Get information about the connected database."""
        return self.adapter.get_database_info()
