"""
Unit tests for NotNullTest.
"""

from unittest.mock import Mock

import pytest

from t4t.testing.standard_tests import NotNullTest


class TestNotNullTest:
    """Test cases for NotNullTest."""

    def test_validate_params_no_column_name(self):
        """Test validation fails without column name in get_test_query."""
        test = NotNullTest()

        # NotNullTest doesn't validate column_name in validate_params, but in get_test_query
        # So we test get_test_query instead
        mock_adapter = Mock()
        with pytest.raises(ValueError, match="requires a column name"):
            test.get_test_query(mock_adapter, "my_table", column_name=None)

    def test_validate_params_with_column_name(self):
        """Test validation passes with column name."""
        test = NotNullTest()

        # Should not raise
        test.validate_params(column_name="id")
        test.validate_params(params={}, column_name="id")

    def test_validate_params_unknown_params(self):
        """Test validation fails with unknown parameters."""
        test = NotNullTest()

        with pytest.raises(ValueError, match="Unknown parameters"):
            test.validate_params(params={"unknown": "value"}, column_name="id")

    def test_get_test_query(self):
        """Test query generation."""
        test = NotNullTest()
        mock_adapter = Mock()
        mock_adapter.generate_not_null_test_query.return_value = (
            "SELECT COUNT(*) FROM table WHERE col IS NULL"
        )

        query = test.get_test_query(mock_adapter, "my_table", column_name="id")

        assert query == "SELECT COUNT(*) FROM table WHERE col IS NULL"
        mock_adapter.generate_not_null_test_query.assert_called_once_with("my_table", "id")

    def test_execute_success(self):
        """Test execution when no NULL values found."""
        test = NotNullTest()
        mock_adapter = Mock()
        mock_adapter.generate_not_null_test_query.return_value = (
            "SELECT COUNT(*) FROM table WHERE id IS NULL"
        )
        mock_adapter.execute_query.return_value = [(0,)]

        result = test.execute(mock_adapter, "my_table", column_name="id")

        assert result.passed is True
        assert result.rows_returned == 0

    def test_execute_failure(self):
        """Test execution when NULL values found."""
        test = NotNullTest()
        mock_adapter = Mock()
        mock_adapter.generate_not_null_test_query.return_value = (
            "SELECT COUNT(*) FROM table WHERE id IS NULL"
        )
        mock_adapter.execute_query.return_value = [(5,)]

        result = test.execute(mock_adapter, "my_table", column_name="id")

        assert result.passed is False
        assert result.rows_returned == 5
