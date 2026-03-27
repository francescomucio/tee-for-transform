"""
Unit tests for UniqueTest.
"""

from unittest.mock import Mock

import pytest

from tee.testing.standard_tests import UniqueTest


class TestUniqueTest:
    """Test cases for UniqueTest."""

    def test_validate_params_column_level(self):
        """Test validation for column-level test."""
        test = UniqueTest()

        # Should not raise
        test.validate_params(column_name="id")

    def test_validate_params_table_level(self):
        """Test validation for table-level test with composite columns."""
        test = UniqueTest()

        # Should not raise
        test.validate_params(params={"columns": ["col1", "col2"]}, column_name=None)

    def test_validate_params_conflict(self):
        """Test validation fails when both column_name and columns param provided."""
        test = UniqueTest()

        with pytest.raises(ValueError, match="cannot use 'columns' param when applied to a column"):
            test.validate_params(params={"columns": ["col1"]}, column_name="id")

    def test_validate_params_empty_columns(self):
        """Test validation fails with empty columns list."""
        test = UniqueTest()

        with pytest.raises(ValueError, match="must be a non-empty list"):
            test.validate_params(params={"columns": []}, column_name=None)

    def test_get_test_query_column_level(self):
        """Test query generation for column-level test."""
        test = UniqueTest()
        mock_adapter = Mock()
        mock_adapter.generate_unique_test_query.return_value = "SELECT COUNT(*) FROM ..."

        test.get_test_query(mock_adapter, "my_table", column_name="id")

        mock_adapter.generate_unique_test_query.assert_called_once_with("my_table", ["id"])

    def test_get_test_query_table_level(self):
        """Test query generation for table-level test."""
        test = UniqueTest()
        mock_adapter = Mock()
        mock_adapter.generate_unique_test_query.return_value = "SELECT COUNT(*) FROM ..."

        test.get_test_query(mock_adapter, "my_table", params={"columns": ["col1", "col2"]})

        mock_adapter.generate_unique_test_query.assert_called_once_with(
            "my_table", ["col1", "col2"]
        )
