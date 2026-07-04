"""
Universal model state management for TEE.

This module provides state tracking for all model types, not just incremental models.
It tracks model execution state, materialization changes, and provides database existence checks.

This is now a wrapper around the centralized StateManager for backward compatibility.
"""

import logging
from typing import Any

from .state_manager import ModelState, StateManager

logger = logging.getLogger(__name__)


class ModelStateManager:
    """
    Universal model state manager for tracking all model types.

    This is a wrapper around the centralized StateManager for backward compatibility.
    """

    def __init__(self, state_database_path: str | None = None, project_folder: str = ".") -> None:
        """
        Initialize the model state manager.

        Args:
            state_database_path: Path to the state database file
            project_folder: Project folder path
        """
        self.state_manager = StateManager(state_database_path, project_folder)
        self.project_folder = project_folder
        self.state_database_path = self.state_manager.state_database_path

    def _get_connection(self) -> Any:
        """Get database connection from the underlying state manager."""
        return self.state_manager._get_connection()

    def _initialize_database(self) -> None:
        """Initialize the state database."""
        self.state_manager._initialize_database()

    def get_model_state(self, model_name: str) -> ModelState | None:
        """Get the current state of a model."""
        return self.state_manager.get_model_state(model_name)

    def save_model_state(
        self,
        model_name: str,
        materialization: str,
        sql_hash: str,
        config_hash: str,
        last_processed_value: str | None = None,
        strategy: str | None = None,
    ) -> None:
        """Save or update model state."""
        self.state_manager.save_model_state(
            model_name, materialization, sql_hash, config_hash, last_processed_value, strategy
        )

    def update_processed_value(
        self, model_name: str, value: str, strategy: str | None = None
    ) -> None:
        """Update the last processed value for a model."""
        self.state_manager.update_processed_value(model_name, value, strategy)

    def check_database_existence(self, adapter: Any, table_name: str) -> bool:
        """Check if the model exists in the target database."""
        return self.state_manager.check_database_existence(adapter, table_name)

    def rebuild_state_from_database(self, adapter: Any, model_name: str) -> ModelState | None:
        """Rebuild model state from database existence."""
        return self.state_manager.rebuild_state_from_database(adapter, model_name)

    def check_materialization_change(
        self, model_name: str, current_materialization: str, behavior: str
    ) -> None:
        """Check if materialization has changed and react based on behavior."""
        self.state_manager.check_materialization_change(
            model_name, current_materialization, behavior
        )

    def get_all_models(self) -> list[ModelState]:
        """Get all model states."""
        return self.state_manager.get_all_models()

    def compute_sql_hash(self, sql_query: str) -> str:
        """Compute hash for SQL query using the centralized state manager."""
        return self.state_manager.compute_sql_hash(sql_query)

    def compute_config_hash(self, config: dict[str, Any]) -> str:
        """Compute hash for configuration using the centralized state manager."""
        return self.state_manager.compute_config_hash(config)

    def close(self) -> None:
        """Close the database connection."""
        self.state_manager.close()
