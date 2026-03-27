"""
Unit tests for HierarchyNoSplitTest.
"""

from unittest.mock import Mock

import pytest

from tee.testing.standard_tests import HierarchyNoSplitTest


class TestHierarchyNoSplitTest:
    """Test cases for HierarchyNoSplitTest."""

    def test_validate_params_no_model_level_column(self):
        """Test validation fails when applied to a column."""
        test = HierarchyNoSplitTest()
        with pytest.raises(ValueError, match="cannot be applied to a column"):
            test.validate_params(
                params={"child_col": "child_id", "parent_col": "parent_id"}, column_name="id"
            )

    def test_validate_params_missing_params(self):
        """Test validation fails without params."""
        test = HierarchyNoSplitTest()
        with pytest.raises(ValueError, match="requires params"):
            test.validate_params(params=None, column_name=None)

    def test_validate_params_missing_child_parent(self):
        """Test validation fails without required keys."""
        test = HierarchyNoSplitTest()
        with pytest.raises(ValueError, match="requires 'child_col' and 'parent_col'"):
            test.validate_params(params={"child_col": "child_id"}, column_name=None)

    def test_get_test_query(self):
        """Test query generation delegates to adapter."""
        test = HierarchyNoSplitTest()
        mock_adapter = Mock()
        mock_adapter.generate_hierarchy_no_split_test_query.return_value = (
            "SELECT COUNT(*) FROM ..."
        )

        query = test.get_test_query(
            mock_adapter,
            "my_table",
            params={"child_col": "child_id", "parent_col": "parent_id"},
        )

        assert query == "SELECT COUNT(*) FROM ..."
        mock_adapter.generate_hierarchy_no_split_test_query.assert_called_once_with(
            table_name="my_table",
            child_col="child_id",
            parent_col="parent_id",
        )

    def test_execute_success(self):
        """Test execution passes when no violations exist."""
        test = HierarchyNoSplitTest()
        mock_adapter = Mock()
        mock_adapter.generate_hierarchy_no_split_test_query.return_value = "SELECT ..."
        mock_adapter.execute_query.return_value = [(0,)]

        result = test.execute(
            mock_adapter,
            table_name="my_table",
            column_name=None,
            params={"child_col": "child_id", "parent_col": "parent_id"},
        )

        assert result.passed is True
        assert result.rows_returned == 0

    def test_execute_failure(self):
        """Test execution fails when violations exist."""
        test = HierarchyNoSplitTest()
        mock_adapter = Mock()
        mock_adapter.generate_hierarchy_no_split_test_query.return_value = "SELECT ..."
        mock_adapter.execute_query.return_value = [(3,)]

        result = test.execute(
            mock_adapter,
            table_name="my_table",
            column_name=None,
            params={"child_col": "child_id", "parent_col": "parent_id"},
        )

        assert result.passed is False
        assert result.rows_returned == 3
