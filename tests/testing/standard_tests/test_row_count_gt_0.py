"""
Unit tests for RowCountGreaterThanZeroTest.
"""

from unittest.mock import Mock

import pytest

from tee.testing.standard_tests import RowCountGreaterThanZeroTest


class TestRowCountGreaterThanZeroTest:
    """Test cases for RowCountGreaterThanZeroTest."""

    def test_validate_params_with_column_name(self):
        """Test validation fails when applied to column."""
        test = RowCountGreaterThanZeroTest()

        with pytest.raises(ValueError, match="is a model-level test"):
            test.validate_params(column_name="id")

    def test_check_passed_inverted_logic(self):
        """Test that check_passed uses inverted logic (count > 0 means pass)."""
        test = RowCountGreaterThanZeroTest()

        assert test.check_passed(0) is False  # Empty table = fail
        assert test.check_passed(1) is True  # Has data = pass
        assert test.check_passed(100) is True  # Has data = pass

    def test_format_message_passed(self):
        """Test message formatting for passed test."""
        test = RowCountGreaterThanZeroTest()

        message = test.format_message(True, 5)
        assert "passed" in message.lower()
        assert "5 row(s)" in message

    def test_format_message_failed(self):
        """Test message formatting for failed test."""
        test = RowCountGreaterThanZeroTest()

        message = test.format_message(False, 0)
        assert "failed" in message.lower()
        assert "empty" in message.lower()

    def test_execute_success(self):
        """Test execution when table has data."""
        test = RowCountGreaterThanZeroTest()
        mock_adapter = Mock()
        mock_adapter.generate_row_count_gt_0_test_query.return_value = "SELECT COUNT(*) FROM table"
        mock_adapter.execute_query.return_value = [(3,)]

        result = test.execute(mock_adapter, "my_table")

        assert result.passed is True
        assert result.rows_returned == 3
        assert "3 row(s)" in result.message

    def test_execute_failure(self):
        """Test execution when table is empty."""
        test = RowCountGreaterThanZeroTest()
        mock_adapter = Mock()
        mock_adapter.generate_row_count_gt_0_test_query.return_value = "SELECT COUNT(*) FROM table"
        mock_adapter.execute_query.return_value = [(0,)]

        result = test.execute(mock_adapter, "my_table")

        assert result.passed is False
        assert result.rows_returned == 0
        assert "empty" in result.message.lower()
