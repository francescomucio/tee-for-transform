"""
Unified connection manager for database adapters.

This module provides a centralized way to manage database connections
for both debug and run commands, eliminating code duplication.
"""

import logging
from typing import Any

from .executor import ModelExecutor


class ConnectionManager:
    """
    Unified connection manager for database operations.

    This class provides a single interface for:
    - Loading project configurations
    - Creating database connections
    - Testing connectivity
    - Managing adapters
    """

    def __init__(
        self,
        project_folder: str,
        connection_config: dict[str, Any],
        variables: dict[str, Any] | None = None,
        env_name: str | None = None,
    ) -> None:
        """
        Initialize the connection manager.

        Args:
            project_folder: Path to the project folder
            connection_config: Database connection configuration
            variables: Optional variables for model execution
            env_name: Environment name for scoping state
        """
        self.project_folder = project_folder
        self.connection_config = connection_config
        self.variables = variables or {}
        self.env_name = env_name
        self.executor = None
        self.logger = logging.getLogger(self.__class__.__name__)

    def create_executor(self) -> ModelExecutor:
        """Create a ModelExecutor instance."""
        if self.executor is None:
            self.executor = ModelExecutor(
                self.project_folder, self.connection_config, env_name=self.env_name
            )
        return self.executor

    def test_connection(self) -> bool:
        """
        Test database connectivity.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            executor = self.create_executor()
            return executor.test_connection()
        except Exception as e:
            self.logger.error(f"Connection test failed: {e}")
            return False

    def get_database_info(self) -> dict[str, Any] | None:
        """Get database information."""
        try:
            executor = self.create_executor()
            return executor.get_database_info()
        except Exception as e:
            self.logger.error(f"Failed to get database info: {e}")
            return None

    def get_supported_materializations(self) -> list[str]:
        """Get list of supported materializations."""
        try:
            executor = self.create_executor()
            return executor.list_supported_materializations()
        except Exception as e:
            self.logger.error(f"Failed to get materializations: {e}")
            return []

    def execute_models(self, parser: Any, _save_analysis: bool = True) -> dict[str, Any]:
        """
        Execute SQL models.

        Args:
            parser: Parser instance with models and execution order
            _save_analysis: Reserved for future analysis export (currently unused)

        Returns:
            Execution results
        """
        try:
            executor = self.create_executor()
            return executor.execute_models(parser, self.variables)
        except Exception as e:
            self.logger.error(f"Model execution failed: {e}")
            raise

    def cleanup(self) -> None:
        """Clean up resources."""
        if self.executor:
            try:
                self.executor.execution_engine.disconnect()
            except Exception as e:
                self.logger.warning(f"Error during cleanup: {e}")
            self.executor = None
