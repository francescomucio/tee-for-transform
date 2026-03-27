"""
Unit tests for AcceptedValuesTest.
"""

from unittest.mock import Mock

import pytest

from tee.testing.standard_tests import AcceptedValuesTest


class TestAcceptedValuesTest:
    """Test cases for AcceptedValuesTest."""

    def test_validate_params_no_column_name(self):
        """Test validation fails without column name."""
        test = AcceptedValuesTest()

        with pytest.raises(ValueError, match="requires a column name"):
            test.validate_params(column_name=None)

    def test_validate_params_no_values(self):
        """Test validation fails without values parameter."""
        test = AcceptedValuesTest()

        with pytest.raises(ValueError, match="requires 'values' parameter"):
            test.validate_params(params={}, column_name="status")

    def test_validate_params_empty_values(self):
        """Test validation fails with empty values list."""
        test = AcceptedValuesTest()

        with pytest.raises(ValueError, match="must contain at least one value"):
            test.validate_params(params={"values": []}, column_name="status")

    def test_validate_params_not_list(self):
        """Test validation fails when values is not a list."""
        test = AcceptedValuesTest()

        with pytest.raises(ValueError, match="must be a list"):
            test.validate_params(params={"values": "not_a_list"}, column_name="status")

    def test_validate_params_valid(self):
        """Test validation passes with valid parameters."""
        test = AcceptedValuesTest()

        # Should not raise
        test.validate_params(params={"values": ["active", "inactive"]}, column_name="status")

    def test_get_test_query(self):
        """Test query generation."""
        test = AcceptedValuesTest()
        mock_adapter = Mock()
        mock_adapter.generate_accepted_values_test_query.return_value = "SELECT COUNT(*) FROM ..."

        test.get_test_query(
            mock_adapter,
            "my_table",
            column_name="status",
            params={"values": ["active", "inactive"]},
        )

        mock_adapter.generate_accepted_values_test_query.assert_called_once_with(
            "my_table", "status", ["active", "inactive"]
        )

    def test_execute_success(self):
        """Test execution when all values are accepted."""
        test = AcceptedValuesTest()
        mock_adapter = Mock()
        mock_adapter.generate_accepted_values_test_query.return_value = "SELECT COUNT(*) FROM ..."
        mock_adapter.execute_query.return_value = [(0,)]

        result = test.execute(
            mock_adapter,
            "my_table",
            column_name="status",
            params={"values": ["active", "inactive"]},
        )

        assert result.passed is True
        assert result.rows_returned == 0

    def test_execute_failure(self):
        """Test execution when invalid values found."""
        test = AcceptedValuesTest()
        mock_adapter = Mock()
        mock_adapter.generate_accepted_values_test_query.return_value = "SELECT COUNT(*) FROM ..."
        mock_adapter.execute_query.return_value = [(2,)]

        result = test.execute(
            mock_adapter,
            "my_table",
            column_name="status",
            params={"values": ["active", "inactive"]},
        )

        assert result.passed is False
        assert result.rows_returned == 2
