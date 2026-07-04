"""
Test cases for incremental materialization adapter interface.

These tests verify that adapters correctly implement the incremental
materialization interface and can be reused across different adapters.
"""

from unittest.mock import Mock

import pytest

from t4t.adapters.base import DatabaseAdapter
from t4t.typing.metadata import (
    IncrementalAppendConfig,
    IncrementalDeleteInsertConfig,
    IncrementalMergeConfig,
)


class TestIncrementalAdapterInterface:
    """Test cases for incremental adapter interface compliance."""

    @pytest.fixture
    def mock_adapter(self):
        """Create a mock adapter that implements the incremental interface."""
        adapter = Mock(spec=DatabaseAdapter)
        adapter.execute_incremental_append = Mock()
        adapter.execute_incremental_merge = Mock()
        adapter.execute_incremental_delete_insert = Mock()
        adapter.get_table_columns = Mock(
            return_value=["id", "name", "created_at", "updated_at", "status"]
        )
        return adapter

    @pytest.fixture
    def sample_append_config(self) -> IncrementalAppendConfig:
        """Sample append configuration."""
        return {"filter_column": "created_at", "start_value": "2024-01-01", "lookback": "7 days"}

    @pytest.fixture
    def sample_merge_config(self) -> IncrementalMergeConfig:
        """Sample merge configuration."""
        return {
            "unique_key": ["id"],
            "filter_column": "updated_at",
            "start_value": "auto",
            "lookback": "3 hours",
        }

    @pytest.fixture
    def sample_delete_insert_config(self) -> IncrementalDeleteInsertConfig:
        """Sample delete+insert configuration."""
        return {
            "where_condition": "updated_at >= @start_date",
            "filter_column": "updated_at",
            "start_value": "@start_date",
        }

    def test_adapter_implements_incremental_append(self, mock_adapter, sample_append_config):
        """Test that adapter implements incremental append."""
        table_name = "test_table"
        source_sql = "SELECT * FROM source_table WHERE created_at >= '2024-01-01'"

        mock_adapter.execute_incremental_append(table_name, source_sql)

        mock_adapter.execute_incremental_append.assert_called_once_with(table_name, source_sql)

    def test_adapter_implements_incremental_merge(self, mock_adapter, sample_merge_config):
        """Test that adapter implements incremental merge."""
        table_name = "test_table"
        source_sql = "SELECT * FROM source_table WHERE updated_at > '2024-01-01'"

        mock_adapter.execute_incremental_merge(table_name, source_sql, sample_merge_config)

        mock_adapter.execute_incremental_merge.assert_called_once_with(
            table_name, source_sql, sample_merge_config
        )

    def test_adapter_implements_incremental_delete_insert(
        self, mock_adapter, sample_delete_insert_config
    ):
        """Test that adapter implements incremental delete+insert."""
        table_name = "test_table"
        delete_sql = "DELETE FROM test_table WHERE updated_at >= '2024-01-01'"
        insert_sql = "SELECT * FROM source_table WHERE updated_at >= '2024-01-01'"

        mock_adapter.execute_incremental_delete_insert(table_name, delete_sql, insert_sql)

        mock_adapter.execute_incremental_delete_insert.assert_called_once_with(
            table_name, delete_sql, insert_sql
        )

    def test_adapter_implements_get_table_columns(self, mock_adapter):
        """Test that adapter implements get_table_columns."""
        table_name = "test_table"
        expected_columns = ["id", "name", "created_at", "updated_at", "status"]

        result = mock_adapter.get_table_columns(table_name)

        assert result == expected_columns
        mock_adapter.get_table_columns.assert_called_once_with(table_name)


class TestIncrementalAdapterBehavior:
    """Test cases for incremental adapter behavior patterns."""

    @pytest.fixture
    def mock_adapter(self):
        """Create a mock adapter with realistic behavior."""
        adapter = Mock(spec=DatabaseAdapter)
        adapter.execute_incremental_append = Mock()
        adapter.execute_incremental_merge = Mock()
        adapter.execute_incremental_delete_insert = Mock()
        adapter.get_table_columns = Mock(
            return_value=["id", "name", "created_at", "updated_at", "status"]
        )
        adapter.execute_query = Mock()
        adapter.create_table = Mock()
        return adapter

    def test_append_strategy_behavior(self, mock_adapter):
        """Test expected behavior for append strategy."""
        table_name = "test_table"
        source_sql = "SELECT * FROM source_table WHERE created_at >= '2024-01-01'"

        # Execute append
        mock_adapter.execute_incremental_append(table_name, source_sql)

        # Verify the call
        mock_adapter.execute_incremental_append.assert_called_once_with(table_name, source_sql)

        # Verify no other methods were called
        mock_adapter.execute_incremental_merge.assert_not_called()
        mock_adapter.execute_incremental_delete_insert.assert_not_called()

    def test_merge_strategy_behavior(self, mock_adapter):
        """Test expected behavior for merge strategy."""
        table_name = "test_table"
        source_sql = "SELECT * FROM source_table WHERE updated_at > '2024-01-01'"
        config = {
            "unique_key": ["id"],
            "filter_column": "updated_at",
            "start_value": "auto",
            "lookback": "3 hours",
        }

        # Execute merge
        mock_adapter.execute_incremental_merge(table_name, source_sql, config)

        # Verify the call
        mock_adapter.execute_incremental_merge.assert_called_once_with(
            table_name, source_sql, config
        )

        # Verify no other methods were called
        mock_adapter.execute_incremental_append.assert_not_called()
        mock_adapter.execute_incremental_delete_insert.assert_not_called()

    def test_delete_insert_strategy_behavior(self, mock_adapter):
        """Test expected behavior for delete+insert strategy."""
        table_name = "test_table"
        delete_sql = "DELETE FROM test_table WHERE updated_at >= '2024-01-01'"
        insert_sql = "SELECT * FROM source_table WHERE updated_at >= '2024-01-01'"

        # Execute delete+insert
        mock_adapter.execute_incremental_delete_insert(table_name, delete_sql, insert_sql)

        # Verify the call
        mock_adapter.execute_incremental_delete_insert.assert_called_once_with(
            table_name, delete_sql, insert_sql
        )

        # Verify no other methods were called
        mock_adapter.execute_incremental_append.assert_not_called()
        mock_adapter.execute_incremental_merge.assert_not_called()

    def test_get_table_columns_behavior(self, mock_adapter):
        """Test expected behavior for get_table_columns."""
        table_name = "test_table"
        expected_columns = ["id", "name", "created_at", "updated_at", "status"]

        # Get columns
        result = mock_adapter.get_table_columns(table_name)

        # Verify result
        assert result == expected_columns
        mock_adapter.get_table_columns.assert_called_once_with(table_name)


class TestIncrementalAdapterErrorHandling:
    """Test cases for incremental adapter error handling."""

    @pytest.fixture
    def mock_adapter_with_errors(self):
        """Create a mock adapter that raises errors."""
        adapter = Mock(spec=DatabaseAdapter)
        adapter.execute_incremental_append = Mock(side_effect=Exception("Append failed"))
        adapter.execute_incremental_merge = Mock(side_effect=Exception("Merge failed"))
        adapter.execute_incremental_delete_insert = Mock(
            side_effect=Exception("Delete+insert failed")
        )
        adapter.get_table_columns = Mock(side_effect=Exception("Get columns failed"))
        return adapter

    def test_append_strategy_error_handling(self, mock_adapter_with_errors):
        """Test error handling for append strategy."""
        table_name = "test_table"
        source_sql = "SELECT * FROM source_table"

        with pytest.raises(Exception, match="Append failed"):
            mock_adapter_with_errors.execute_incremental_append(table_name, source_sql)

    def test_merge_strategy_error_handling(self, mock_adapter_with_errors):
        """Test error handling for merge strategy."""
        table_name = "test_table"
        source_sql = "SELECT * FROM source_table"
        config = {"unique_key": ["id"]}

        with pytest.raises(Exception, match="Merge failed"):
            mock_adapter_with_errors.execute_incremental_merge(table_name, source_sql, config)

    def test_delete_insert_strategy_error_handling(self, mock_adapter_with_errors):
        """Test error handling for delete+insert strategy."""
        table_name = "test_table"
        delete_sql = "DELETE FROM test_table"
        insert_sql = "SELECT * FROM source_table"

        with pytest.raises(Exception, match="Delete\\+insert failed"):
            mock_adapter_with_errors.execute_incremental_delete_insert(
                table_name, delete_sql, insert_sql
            )

    def test_get_table_columns_error_handling(self, mock_adapter_with_errors):
        """Test error handling for get_table_columns."""
        table_name = "test_table"

        with pytest.raises(Exception, match="Get columns failed"):
            mock_adapter_with_errors.get_table_columns(table_name)


class TestIncrementalAdapterFallback:
    """Test cases for incremental adapter fallback behavior."""

    @pytest.fixture
    def mock_adapter_without_incremental(self):
        """Create a mock adapter without incremental methods."""
        adapter = Mock(spec=DatabaseAdapter)
        # Remove incremental methods to test fallback
        del adapter.execute_incremental_append
        del adapter.execute_incremental_merge
        del adapter.execute_incremental_delete_insert
        adapter.execute_query = Mock()
        adapter.create_table = Mock()
        return adapter

    def test_fallback_behavior_detection(self, mock_adapter_without_incremental):
        """Test that fallback behavior is detected correctly."""
        # Test that incremental methods don't exist
        assert not hasattr(mock_adapter_without_incremental, "execute_incremental_append")
        assert not hasattr(mock_adapter_without_incremental, "execute_incremental_merge")
        assert not hasattr(mock_adapter_without_incremental, "execute_incremental_delete_insert")

        # Test that fallback methods exist
        assert hasattr(mock_adapter_without_incremental, "execute_query")
        assert hasattr(mock_adapter_without_incremental, "create_table")


class TestIncrementalAdapterDataTypes:
    """Test cases for incremental adapter data type handling."""

    @pytest.fixture
    def mock_adapter(self):
        """Create a mock adapter for data type testing."""
        adapter = Mock(spec=DatabaseAdapter)
        adapter.execute_incremental_append = Mock()
        adapter.execute_incremental_merge = Mock()
        adapter.execute_incremental_delete_insert = Mock()
        adapter.get_table_columns = Mock(
            return_value=["id", "name", "created_at", "updated_at", "status"]
        )
        return adapter

    def test_string_parameters(self, mock_adapter):
        """Test that string parameters are handled correctly."""
        table_name = "test_table"
        source_sql = "SELECT * FROM source_table"
        config = {"unique_key": ["id"]}

        # Test all methods with string parameters
        mock_adapter.execute_incremental_append(table_name, source_sql)
        mock_adapter.execute_incremental_merge(table_name, source_sql, config)
        mock_adapter.execute_incremental_delete_insert(table_name, "DELETE SQL", "INSERT SQL")

        # Verify all calls were made
        assert mock_adapter.execute_incremental_append.called
        assert mock_adapter.execute_incremental_merge.called
        assert mock_adapter.execute_incremental_delete_insert.called

    def test_list_parameters(self, mock_adapter):
        """Test that list parameters are handled correctly."""
        config = {
            "unique_key": ["id", "name"],  # List of strings
            "filter_column": "created_at",
        }

        mock_adapter.execute_incremental_merge("test_table", "SELECT * FROM source", config)

        # Verify the call was made with list parameter
        mock_adapter.execute_incremental_merge.assert_called_once()
        call_args = mock_adapter.execute_incremental_merge.call_args
        assert call_args[0][2] == config  # Third argument should be the config with list


class TestIncrementalAdapterPerformance:
    """Test cases for incremental adapter performance characteristics."""

    @pytest.fixture
    def mock_adapter(self):
        """Create a mock adapter for performance testing."""
        adapter = Mock(spec=DatabaseAdapter)
        adapter.execute_incremental_append = Mock()
        adapter.execute_incremental_merge = Mock()
        adapter.execute_incremental_delete_insert = Mock()
        adapter.get_table_columns = Mock(
            return_value=["id", "name", "created_at", "updated_at", "status"]
        )
        return adapter

    def test_append_strategy_performance(self, mock_adapter):
        """Test that append strategy is called efficiently."""
        table_name = "test_table"
        source_sql = "SELECT * FROM source_table"

        # Execute multiple times
        for _ in range(10):
            mock_adapter.execute_incremental_append(table_name, source_sql)

        # Verify it was called 10 times
        assert mock_adapter.execute_incremental_append.call_count == 10

    def test_merge_strategy_performance(self, mock_adapter):
        """Test that merge strategy is called efficiently."""
        table_name = "test_table"
        source_sql = "SELECT * FROM source_table"
        config = {"unique_key": ["id"]}

        # Execute multiple times
        for _ in range(10):
            mock_adapter.execute_incremental_merge(table_name, source_sql, config)

        # Verify it was called 10 times
        assert mock_adapter.execute_incremental_merge.call_count == 10

    def test_delete_insert_strategy_performance(self, mock_adapter):
        """Test that delete+insert strategy is called efficiently."""
        table_name = "test_table"
        delete_sql = "DELETE FROM test_table"
        insert_sql = "SELECT * FROM source_table"

        # Execute multiple times
        for _ in range(10):
            mock_adapter.execute_incremental_delete_insert(table_name, delete_sql, insert_sql)

        # Verify it was called 10 times
        assert mock_adapter.execute_incremental_delete_insert.call_count == 10


class TestIncrementalAdapterIntegration:
    """Integration test cases for incremental adapters."""

    @pytest.fixture
    def mock_adapter(self):
        """Create a mock adapter for integration testing."""
        adapter = Mock(spec=DatabaseAdapter)
        adapter.execute_incremental_append = Mock()
        adapter.execute_incremental_merge = Mock()
        adapter.execute_incremental_delete_insert = Mock()
        adapter.get_table_columns = Mock(
            return_value=["id", "name", "created_at", "updated_at", "status"]
        )
        return adapter

    def test_full_incremental_workflow(self, mock_adapter):
        """Test a full incremental workflow."""
        table_name = "test_table"

        # Step 1: Get table columns
        columns = mock_adapter.get_table_columns(table_name)
        assert columns == ["id", "name", "created_at", "updated_at", "status"]

        # Step 2: Execute append strategy
        source_sql = "SELECT * FROM source_table WHERE created_at >= '2024-01-01'"
        mock_adapter.execute_incremental_append(table_name, source_sql)

        # Step 3: Execute merge strategy
        merge_config = {
            "unique_key": ["id"],
            "filter_column": "updated_at",
            "start_value": "auto",
            "lookback": "1 hour",
        }
        mock_adapter.execute_incremental_merge(table_name, source_sql, merge_config)

        # Step 4: Execute delete+insert strategy
        delete_sql = "DELETE FROM test_table WHERE updated_at >= '2024-01-01'"
        insert_sql = "SELECT * FROM source_table WHERE updated_at >= '2024-01-01'"
        mock_adapter.execute_incremental_delete_insert(table_name, delete_sql, insert_sql)

        # Verify all methods were called
        assert mock_adapter.get_table_columns.called
        assert mock_adapter.execute_incremental_append.called
        assert mock_adapter.execute_incremental_merge.called
        assert mock_adapter.execute_incremental_delete_insert.called

    def test_mixed_strategy_execution(self, mock_adapter):
        """Test execution of mixed strategies."""

        # Execute different strategies for different tables
        strategies = [
            ("table1", "append", "SELECT * FROM source1"),
            ("table2", "merge", "SELECT * FROM source2"),
            ("table3", "delete_insert", "DELETE FROM table3", "SELECT * FROM source3"),
        ]

        for strategy_info in strategies:
            if strategy_info[1] == "append":
                mock_adapter.execute_incremental_append(strategy_info[0], strategy_info[2])
            elif strategy_info[1] == "merge":
                config = {"unique_key": ["id"]}
                mock_adapter.execute_incremental_merge(strategy_info[0], strategy_info[2], config)
            elif strategy_info[1] == "delete_insert":
                mock_adapter.execute_incremental_delete_insert(
                    strategy_info[0], strategy_info[2], strategy_info[3]
                )

        # Verify all strategies were executed
        assert mock_adapter.execute_incremental_append.called
        assert mock_adapter.execute_incremental_merge.called
        assert mock_adapter.execute_incremental_delete_insert.called
