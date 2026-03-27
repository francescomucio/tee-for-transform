"""
Test cases for get_time_filter_condition method.
"""

from datetime import datetime, timedelta
from unittest.mock import patch

from tests.engine.incremental.test_executor_base import TestIncrementalExecutor


class TestTimeFilterCondition(TestIncrementalExecutor):
    """Test cases for get_time_filter_condition method."""

    def test_with_last_processed_value(self, executor, sample_append_config):
        """Test time filter with last processed value."""
        result = executor.get_time_filter_condition(
            sample_append_config, last_processed_value="2024-01-15"
        )

        assert result == "created_at > '2024-01-15'"

    def test_auto_start_value_with_table_name(self, executor):
        """Test auto start_value with table name."""
        from unittest.mock import Mock

        config = {"filter_column": "updated_at", "start_value": "auto"}
        mock_adapter = Mock()
        # Adapter returns a mapping of column_name -> datatype in production
        mock_adapter.get_table_columns = Mock(
            return_value={"id": "int", "updated_at": "timestamp", "value": "string"}
        )
        result = executor.get_time_filter_condition(
            config, table_name="my_schema.test_table", table_exists=True, adapter=mock_adapter
        )

        expected = "updated_at > (SELECT MAX(updated_at) FROM my_schema.test_table)"
        assert result == expected

    def test_auto_start_value_with_lookback(self, executor):
        """Test auto start_value with lookback."""
        from unittest.mock import Mock

        config = {"filter_column": "updated_at", "start_value": "auto", "lookback": "3 hours"}
        mock_adapter = Mock()
        mock_adapter.get_table_columns = Mock(
            return_value={"id": "int", "updated_at": "timestamp", "value": "string"}
        )
        result = executor.get_time_filter_condition(
            config, table_name="my_schema.test_table", table_exists=True, adapter=mock_adapter
        )

        expected = (
            "updated_at > (SELECT MAX(updated_at) - INTERVAL '3 hours' FROM my_schema.test_table)"
        )
        assert result == expected

    def test_current_date_start_value(self, executor, sample_append_config):
        """Test CURRENT_DATE start_value."""
        config = {"filter_column": "created_at", "start_value": "CURRENT_DATE"}

        result = executor.get_time_filter_condition(config)

        assert result == "created_at >= CURRENT_DATE"

    def test_specific_date_start_value(self, executor, sample_append_config):
        """Test specific date start_value."""
        result = executor.get_time_filter_condition(sample_append_config)

        assert result == "created_at >= '2024-01-01'"

    def test_variable_resolution(self, executor):
        """Test variable resolution in start_value."""
        config = {"filter_column": "created_at", "start_value": "@start_date"}
        variables = {"start_date": "2024-02-01"}

        result = executor.get_time_filter_condition(config, variables=variables)

        assert result == "created_at >= '2024-02-01'"

    def test_variable_resolution_with_braces(self, executor):
        """Test variable resolution with {{ }} syntax."""
        config = {"filter_column": "created_at", "start_value": "{{ start_date }}"}
        variables = {"start_date": "2024-02-01"}

        result = executor.get_time_filter_condition(config, variables=variables)

        assert result == "created_at >= '2024-02-01'"

    def test_default_lookback_when_no_start_value(self, executor):
        """Test default 7-day lookback when no start_value specified."""
        config = {"filter_column": "created_at"}

        with patch("tee.engine.materialization.incremental_executor.datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime(2024, 1, 15)
            mock_datetime.timedelta = timedelta

            result = executor.get_time_filter_condition(config)

            assert result == "created_at >= '2024-01-08'"  # 7 days before 2024-01-15

    def test_auto_start_value_uses_destination_filter_column(self, executor):
        """If destination_filter_column is set, use it for the MAX() subquery."""
        from unittest.mock import Mock

        config = {
            "filter_column": "created_date",
            "destination_filter_column": "created_dt",
            "start_value": "auto",
        }
        mock_adapter = Mock()
        mock_adapter.get_table_columns = Mock(
            return_value={"created_dt": "timestamp", "other": "string"}
        )

        result = executor.get_time_filter_condition(
            config, table_name="my_schema.dim_brand", table_exists=True, adapter=mock_adapter
        )

        assert result == "created_date > (SELECT MAX(created_dt) FROM my_schema.dim_brand)"

    def test_destination_filter_column_missing_raises(self, executor):
        """If destination_filter_column is set but missing in target schema, raise an error."""
        from unittest.mock import Mock

        config = {
            "filter_column": "created_date",
            "destination_filter_column": "created_dt",
            "start_value": "auto",
        }
        mock_adapter = Mock()
        mock_adapter.get_table_columns = Mock(return_value={"created_date": "timestamp"})

        import pytest

        with pytest.raises(ValueError, match="destination_filter_column"):
            executor.get_time_filter_condition(
                config, table_name="my_schema.dim_brand", table_exists=True, adapter=mock_adapter
            )
