"""
Test cases for should_run_incremental method.
"""

from datetime import datetime

from tee.engine.model_state import ModelState
from tests.engine.incremental.test_executor_base import TestIncrementalExecutor


class TestShouldRunIncremental(TestIncrementalExecutor):
    """Test cases for should_run_incremental method."""

    def test_no_state_exists_runs_full_load(self, executor, sample_incremental_config):
        """Test that full load runs when no state exists."""
        executor.state_manager.get_model_state.return_value = None

        result = executor.should_run_incremental(
            "test_model", "SELECT * FROM test", sample_incremental_config
        )

        assert result is False
        executor.state_manager.get_model_state.assert_called_once_with("test_model")

    def test_unknown_hashes_runs_full_load(self, executor, sample_incremental_config):
        """Test that full load runs when hashes are unknown."""
        state = ModelState(
            model_name="test_model",
            materialization="incremental",
            last_execution_timestamp=datetime.now(),
            sql_hash="unknown",
            config_hash="unknown",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            last_processed_value=None,
            strategy="append",
        )
        executor.state_manager.get_model_state.return_value = state

        result = executor.should_run_incremental(
            "test_model", "SELECT * FROM test", sample_incremental_config
        )

        assert result is False

    def test_model_definition_changed_runs_full_load(self, executor, sample_incremental_config):
        """Test that full load runs when model definition changes."""
        state = ModelState(
            model_name="test_model",
            materialization="incremental",
            last_execution_timestamp=datetime.now(),
            sql_hash="old_hash",
            config_hash="old_hash",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            last_processed_value="2024-01-01",
            strategy="append",
        )
        executor.state_manager.get_model_state.return_value = state
        executor.state_manager.compute_sql_hash.return_value = "new_hash"
        executor.state_manager.compute_config_hash.return_value = "old_hash"

        result = executor.should_run_incremental(
            "test_model", "SELECT * FROM test", sample_incremental_config
        )

        assert result is False

    def test_append_strategy_runs_incremental(self, executor, sample_incremental_config):
        """Test that append strategy runs incrementally."""
        state = ModelState(
            model_name="test_model",
            materialization="incremental",
            last_execution_timestamp=datetime.now(),
            sql_hash="test_sql_hash",
            config_hash="test_config_hash",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            last_processed_value="2024-01-01",
            strategy="append",
        )
        executor.state_manager.get_model_state.return_value = state

        result = executor.should_run_incremental(
            "test_model", "SELECT * FROM test", sample_incremental_config
        )

        assert result is True

    def test_merge_strategy_with_auto_start_date_runs_incremental(self, executor):
        """Test that merge strategy with auto start_date runs incrementally."""
        config = {
            "strategy": "merge",
            "merge": {"unique_key": ["id"], "filter_column": "updated_at", "start_value": "auto"},
        }
        state = ModelState(
            model_name="test_model",
            materialization="incremental",
            last_execution_timestamp=datetime.now(),
            sql_hash="test_sql_hash",
            config_hash="test_config_hash",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            last_processed_value=None,
            strategy="merge",
        )
        executor.state_manager.get_model_state.return_value = state

        result = executor.should_run_incremental("test_model", "SELECT * FROM test", config)

        assert result is True

    def test_merge_strategy_with_variable_start_date_runs_incremental(self, executor):
        """Test that merge strategy with variable start_date runs incrementally."""
        config = {
            "strategy": "merge",
            "merge": {
                "unique_key": ["id"],
                "filter_column": "updated_at",
                "start_value": "@start_date",
            },
        }
        state = ModelState(
            model_name="test_model",
            materialization="incremental",
            last_execution_timestamp=datetime.now(),
            sql_hash="test_sql_hash",
            config_hash="test_config_hash",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            last_processed_value=None,
            strategy="merge",
        )
        executor.state_manager.get_model_state.return_value = state

        result = executor.should_run_incremental("test_model", "SELECT * FROM test", config)

        assert result is True

    def test_merge_strategy_without_last_processed_value_runs_full_load(self, executor):
        """Test that merge strategy without last_processed_value runs full load."""
        config = {
            "strategy": "merge",
            "merge": {
                "unique_key": ["id"],
                "filter_column": "updated_at",
                "start_value": "2024-01-01",
            },
        }
        state = ModelState(
            model_name="test_model",
            materialization="incremental",
            last_execution_timestamp=datetime.now(),
            sql_hash="test_hash",
            config_hash="test_hash",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            last_processed_value=None,
            strategy="merge",
        )
        executor.state_manager.get_model_state.return_value = state

        result = executor.should_run_incremental("test_model", "SELECT * FROM test", config)

        assert result is False
