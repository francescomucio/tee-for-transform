"""State checking and management for models."""

import logging
from typing import Any

from ..model_state import ModelStateManager

logger = logging.getLogger(__name__)


class StateChecker:
    """Manages model state checking and updates."""

    def __init__(self, project_folder: str) -> None:
        """
        Initialize the state checker.

        Args:
            project_folder: Project folder path for state management
        """
        self.state_manager = ModelStateManager(project_folder=project_folder)
        self.project_folder = project_folder

    def generate_sql_hash(self, sql_query: str) -> str:
        """
        Generate a hash for SQL content using the centralized state manager.

        Args:
            sql_query: SQL query string

        Returns:
            Hash string
        """
        return self.state_manager.compute_sql_hash(sql_query)

    def generate_config_hash(self, metadata: dict[str, Any] | None) -> str:
        """
        Generate a hash for model configuration using the centralized state manager.

        Args:
            metadata: Model metadata dictionary

        Returns:
            Hash string
        """
        if not metadata:
            return self.state_manager.compute_config_hash({})
        return self.state_manager.compute_config_hash(metadata)

    def check_model_state(
        self,
        table_name: str,
        materialization: str,
        _metadata: dict[str, Any] | None,
        adapter: Any | None = None,
    ) -> None:
        """
        Check model state for materialization changes and database existence.

        Args:
            table_name: Name of the model
            materialization: Materialization type
            _metadata: Model metadata (reserved for future state logic)
            adapter: Optional database adapter for existence checking
        """
        # Check if model exists in state
        state = self.state_manager.get_model_state(table_name)

        if state is None:
            # Model doesn't exist in state, check if it exists in database
            if adapter and self.state_manager.check_database_existence(adapter, table_name):
                logger.warning(
                    f"Model {table_name} exists in database but not in state. Rebuilding state..."
                )
                self.state_manager.rebuild_state_from_database(adapter, table_name)
        else:
            # Check for materialization changes
            flags = self._load_flags()
            behavior = flags.get("materialization_change_behavior", "warn")
            self.state_manager.check_materialization_change(table_name, materialization, behavior)

    def _load_flags(self) -> dict[str, Any]:
        """Load flags from project configuration."""
        try:
            from ..config import load_database_config

            config = load_database_config("default", self.project_folder)
            if hasattr(config, "extra") and config.extra:
                return config.extra.get("flags", {})
        except Exception as e:
            logger.debug(f"Could not load flags: {e}")

        return {}

    def save_model_state(
        self,
        table_name: str,
        materialization: str,
        sql_query: str,
        metadata: dict[str, Any] | None,
    ) -> None:
        """
        Save model state after successful execution.

        Args:
            table_name: Name of the model
            materialization: Materialization type
            sql_query: SQL query string
            metadata: Model metadata
        """
        sql_hash = self.generate_sql_hash(sql_query)

        # Extract incremental-specific data if applicable
        last_processed_value = None
        strategy = None
        config_hash = None

        if materialization == "incremental" and metadata:
            incremental_config = metadata.get("incremental", {})
            if incremental_config:
                strategy = incremental_config.get("strategy")
                # For incremental models, compute config hash from incremental config only
                config_hash = self.generate_config_hash(incremental_config)
                # For incremental models, we might want to track the last processed value
                # This would be set by the incremental executor
            else:
                config_hash = self.generate_config_hash(metadata)
        else:
            config_hash = self.generate_config_hash(metadata)

        self.state_manager.save_model_state(
            model_name=table_name,
            materialization=materialization,
            sql_hash=sql_hash,
            config_hash=config_hash,
            last_processed_value=last_processed_value,
            strategy=strategy,
        )

        logger.debug(f"Saved state for model: {table_name}")

    def close(self) -> None:
        """Close the state manager."""
        self.state_manager.close()
