"""
Unit tests for LevelUniquenessTest.
"""

from unittest.mock import Mock

import pytest

from tee.testing.standard_tests import LevelUniquenessTest


class TestLevelUniquenessTest:
    """Test cases for LevelUniquenessTest."""

    def test_validate_params_no_model_level_column(self):
        """Test validation fails when applied to a column."""
        test = LevelUniquenessTest()
        with pytest.raises(ValueError, match="cannot be applied to a column"):
            test.validate_params(
                params={"pk_col": "id", "attribute_cols": ["name"]}, column_name="id"
            )

    def test_validate_params_missing_params(self):
        """Test validation fails without params."""
        test = LevelUniquenessTest()
        with pytest.raises(ValueError, match="requires params"):
            test.validate_params(params=None, column_name=None)

    def test_validate_params_missing_keys(self):
        """Test validation fails without required keys."""
        test = LevelUniquenessTest()
        with pytest.raises(ValueError, match="requires 'pk_col' and 'attribute_cols'"):
            test.validate_params(params={"pk_col": "id"}, column_name=None)

    def test_get_test_query(self):
        """Test query generation delegates to adapter."""
        test = LevelUniquenessTest()
        mock_adapter = Mock()
        mock_adapter.generate_level_uniqueness_test_query.return_value = "SELECT COUNT(*) FROM ..."

        query = test.get_test_query(
            mock_adapter,
            "my_table",
            params={"pk_col": "level_id", "attribute_cols": ["a", "b"]},
        )

        assert query == "SELECT COUNT(*) FROM ..."
        mock_adapter.generate_level_uniqueness_test_query.assert_called_once_with(
            table_name="my_table",
            pk_col="level_id",
            attribute_cols=["a", "b"],
        )

    def test_execute_success(self):
        """Test execution passes when no violations exist."""
        test = LevelUniquenessTest()
        mock_adapter = Mock()
        mock_adapter.generate_level_uniqueness_test_query.return_value = "SELECT ..."
        mock_adapter.execute_query.return_value = [(0,)]

        result = test.execute(
            mock_adapter,
            table_name="my_table",
            column_name=None,
            params={"pk_col": "level_id", "attribute_cols": ["a"]},
        )

        assert result.passed is True
        assert result.rows_returned == 0

    def test_execute_failure(self):
        """Test execution fails when violations exist."""
        test = LevelUniquenessTest()
        mock_adapter = Mock()
        mock_adapter.generate_level_uniqueness_test_query.return_value = "SELECT ..."
        mock_adapter.execute_query.return_value = [(2,)]

        result = test.execute(
            mock_adapter,
            table_name="my_table",
            column_name=None,
            params={"pk_col": "level_id", "attribute_cols": ["a"]},
        )

        assert result.passed is False
        assert result.rows_returned == 2
