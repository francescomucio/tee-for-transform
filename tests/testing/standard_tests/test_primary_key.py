"""
Unit tests for PrimaryKeyTest.
"""

from unittest.mock import Mock

import pytest

from tee.testing.standard_tests import PrimaryKeyTest


class TestPrimaryKeyTest:
    """Test cases for PrimaryKeyTest."""

    def test_validate_params_no_column_name(self):
        """Test validation fails without column name."""
        test = PrimaryKeyTest()
        with pytest.raises(ValueError, match="requires a column name"):
            test.validate_params(column_name=None)

    def test_validate_params_valid(self):
        """Test validation passes with column name."""
        test = PrimaryKeyTest()
        test.validate_params(column_name="id")

    def test_get_test_query(self):
        """Test query generation delegates to adapter."""
        test = PrimaryKeyTest()
        mock_adapter = Mock()
        mock_adapter.generate_primary_key_test_query.return_value = "SELECT COUNT(*) FROM ..."

        query = test.get_test_query(mock_adapter, "my_table", column_name="id")

        assert query == "SELECT COUNT(*) FROM ..."
        mock_adapter.generate_primary_key_test_query.assert_called_once_with("my_table", "id")

    def test_execute_success(self):
        """Test execution passes when no violations."""
        test = PrimaryKeyTest()
        mock_adapter = Mock()
        mock_adapter.generate_primary_key_test_query.return_value = "SELECT ..."
        mock_adapter.execute_query.return_value = [(0,)]

        result = test.execute(mock_adapter, "my_table", column_name="id")

        assert result.passed is True
        assert result.rows_returned == 0

    def test_execute_failure(self):
        """Test execution fails when violations exist."""
        test = PrimaryKeyTest()
        mock_adapter = Mock()
        mock_adapter.generate_primary_key_test_query.return_value = "SELECT ..."
        mock_adapter.execute_query.return_value = [(5,)]

        result = test.execute(mock_adapter, "my_table", column_name="id")

        assert result.passed is False
        assert result.rows_returned == 5
