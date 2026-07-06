"""
Centralized state management for t4t models.

This module provides a unified interface for managing model state across
both parsing and execution phases, ensuring consistent hash computation
and state tracking.
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

logger = logging.getLogger(__name__)


@dataclass
class ModelState:
    """Represents the state of a model in the system."""

    model_name: str
    materialization: str
    last_execution_timestamp: str
    sql_hash: str
    config_hash: str
    created_at: str
    updated_at: str
    last_processed_value: str | None = None
    strategy: str | None = None


class StateManager:
    """
    Centralized state management for t4t models.

    This class provides a unified interface for managing model state across
    both parsing and execution phases, ensuring consistent hash computation
    and state tracking.
    """

    def __init__(
        self,
        state_database_path: str | None = None,
        project_folder: str = ".",
        environment: str | None = None,
    ) -> None:
        """
        Initialize the state manager.

        Args:
            state_database_path: Path to the state database file
            project_folder: Project folder path
            environment: Environment name for scoping state
        """
        self.project_folder = Path(project_folder)
        self.environment = environment
        if state_database_path:
            self.state_database_path = Path(state_database_path)
        else:
            self.state_database_path = self.project_folder / "data" / "t4t_state.db"

        # Ensure parent directory exists
        self.state_database_path.parent.mkdir(parents=True, exist_ok=True)

        self.conn = None
        self._initialize_database()
        logger.info(f"State manager initialized with database: {self.state_database_path}")

    def _get_connection(self) -> Any:
        """Get database connection, creating if needed."""
        if self.conn is None:
            self.conn = duckdb.connect(database=str(self.state_database_path), read_only=False)
        return self.conn

    def _initialize_database(self) -> None:
        """Initialize the state database with required tables."""
        conn = self._get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tee_model_state (
                model_name VARCHAR NOT NULL,
                materialization VARCHAR NOT NULL,
                last_execution_timestamp VARCHAR,
                sql_hash VARCHAR,
                config_hash VARCHAR,
                created_at VARCHAR,
                updated_at VARCHAR,
                last_processed_value VARCHAR,
                strategy VARCHAR,
                environment VARCHAR DEFAULT 'default',
                PRIMARY KEY (model_name, environment)
            )
        """)
        conn.commit()

    def compute_sql_hash(self, sql_query: str) -> str:
        """Compute hash for SQL query."""
        return hashlib.sha256(sql_query.encode("utf-8")).hexdigest()

    def compute_config_hash(self, config: dict[str, Any]) -> str:
        """Compute hash for configuration using JSON serialization."""
        if not config:
            return hashlib.sha256(b"").hexdigest()

        # Use JSON serialization for deterministic hashing
        config_str = json.dumps(config, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(config_str.encode("utf-8")).hexdigest()

    def get_model_state(self, model_name: str) -> ModelState | None:
        """Get the current state of a model."""
        conn = self._get_connection()
        query = "SELECT * FROM tee_model_state WHERE model_name = ? AND environment = ?"
        result = conn.execute(query, [model_name, self.environment or "default"]).fetchone()
        if result is None:
            return None

        return ModelState(
            model_name=result[0],
            materialization=result[1],
            last_execution_timestamp=result[2],
            sql_hash=result[3],
            config_hash=result[4],
            created_at=result[5],
            updated_at=result[6],
            last_processed_value=result[7],
            strategy=result[8],
        )

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
        conn = self._get_connection()
        now = datetime.now(UTC).isoformat()
        env = self.environment or "default"

        # Check if model exists
        existing_state = self.get_model_state(model_name)

        if existing_state:
            # Update existing state
            update_sql = """
                UPDATE tee_model_state
                SET materialization = ?, last_execution_timestamp = ?, sql_hash = ?,
                    config_hash = ?, updated_at = ?, last_processed_value = ?, strategy = ?
                WHERE model_name = ? AND environment = ?
            """
            conn.execute(
                update_sql,
                [
                    materialization,
                    now,
                    sql_hash,
                    config_hash,
                    now,
                    last_processed_value,
                    strategy,
                    model_name,
                    env,
                ],
            )
            logger.debug(f"Updated state for model: {model_name}")
        else:
            # Insert new state
            insert_sql = """
                INSERT INTO tee_model_state
                (model_name, materialization, last_execution_timestamp, sql_hash, config_hash,
                 created_at, updated_at, last_processed_value, strategy, environment)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            conn.execute(
                insert_sql,
                [
                    model_name,
                    materialization,
                    now,
                    sql_hash,
                    config_hash,
                    now,
                    now,
                    last_processed_value,
                    strategy,
                    env,
                ],
            )
            logger.debug(f"Created new state for model: {model_name}")

        conn.commit()

    def update_processed_value(
        self, model_name: str, value: str, strategy: str | None = None
    ) -> None:
        """Update the last processed value for a model."""
        state = self.get_model_state(model_name)
        if state is None:
            # State doesn't exist yet - this happens on first run after a full load
            # Create the state with default values so we can track the processed value
            logger.info(
                f"Model state doesn't exist for {model_name}, creating it with processed value: {value}"
            )
            self.save_model_state(
                model_name=model_name,
                materialization="incremental",  # Default to incremental since this is called from incremental materialization
                sql_hash="unknown",  # Will be updated on next run when we have the SQL hash
                config_hash="unknown",  # Will be updated on next run when we have the config hash
                last_processed_value=value,
                strategy=strategy,
            )
            return

        logger.info(
            f"Updating processed value for {model_name}: {state.last_processed_value} -> {value}"
        )

        # Update the state with new processed value
        datetime.now(UTC).isoformat()
        self.save_model_state(
            model_name=model_name,
            materialization=state.materialization,
            sql_hash=state.sql_hash,
            config_hash=state.config_hash,
            last_processed_value=value,
            strategy=strategy or state.strategy,
        )

    def check_database_existence(self, adapter: Any, table_name: str) -> bool:
        """Check if the model exists in the target database."""
        # Check if table exists
        if adapter.table_exists(table_name):
            return True

        # Check if view exists (if the adapter supports it)
        if hasattr(adapter, "view_exists"):
            return adapter.view_exists(table_name)

        # For adapters without view_exists method, assume it doesn't exist
        return False

    def rebuild_state_from_database(self, adapter: Any, model_name: str) -> ModelState | None:
        """Rebuild model state from database existence."""
        if not self.check_database_existence(adapter, model_name):
            return None

        # Create a basic state entry for existing models
        now = datetime.now(UTC).isoformat()
        state = ModelState(
            model_name=model_name,
            materialization="unknown",  # We don't know the original materialization
            last_execution_timestamp=now,
            sql_hash="unknown",
            config_hash="unknown",
            created_at=now,
            updated_at=now,
        )

        # Save the rebuilt state with unknown values initially
        # The actual hashes will be computed and updated during execution
        self.save_model_state(
            model_name=model_name,
            materialization="unknown",
            sql_hash="unknown",
            config_hash="unknown",
        )

        logger.info(f"Rebuilt state for existing model: {model_name}")
        return state

    def check_materialization_change(
        self, model_name: str, current_materialization: str, behavior: str
    ) -> None:
        """Check if materialization has changed and react based on behavior."""
        state = self.get_model_state(model_name)
        if state and state.materialization != current_materialization:
            message = f"Materialization changed for {model_name}: {state.materialization} -> {current_materialization}"
            if behavior == "warn":
                logger.warning(message)
            elif behavior == "error":
                logger.error(message)
                raise ValueError(message)
            elif behavior == "ignore":
                logger.info(f"Ignoring materialization change for {model_name}")

    def get_all_models(self) -> list[ModelState]:
        """Get all model states for the current environment."""
        conn = self._get_connection()
        query = "SELECT * FROM tee_model_state WHERE environment = ? ORDER BY model_name"
        results = conn.execute(query, [self.environment or "default"]).fetchall()

        return [
            ModelState(
                model_name=row[0],
                materialization=row[1],
                last_execution_timestamp=row[2],
                sql_hash=row[3],
                config_hash=row[4],
                created_at=row[5],
                updated_at=row[6],
                last_processed_value=row[7],
                strategy=row[8],
            )
            for row in results
        ]

    def close(self) -> None:
        """Close the database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None
            logger.debug("State manager connection closed.")
