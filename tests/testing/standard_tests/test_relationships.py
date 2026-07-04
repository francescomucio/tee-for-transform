"""
Unit tests for RelationshipsTest.
"""

from unittest.mock import Mock

import pytest

from t4t.testing.standard_tests import RelationshipsTest


class TestRelationshipsTest:
    """Test cases for RelationshipsTest."""

    def test_validate_params_no_column_name(self):
        """Test validation fails without column name."""
        test = RelationshipsTest()

        with pytest.raises(ValueError, match="requires a column name"):
            test.validate_params(column_name=None)

    def test_validate_params_no_params(self):
        """Test validation fails without parameters."""
        test = RelationshipsTest()

        with pytest.raises(
            ValueError, match="requires 'to' and 'field' parameters|requires 'to' parameter"
        ):
            test.validate_params(params={}, column_name="user_id")

    def test_validate_params_missing_to(self):
        """Test validation fails without 'to' parameter."""
        test = RelationshipsTest()

        with pytest.raises(ValueError, match="requires 'to' parameter"):
            test.validate_params(params={"field": "id"}, column_name="user_id")

    def test_validate_params_missing_field(self):
        """Test validation fails without 'field' or 'fields' parameter."""
        test = RelationshipsTest()

        with pytest.raises(ValueError, match="requires 'field' or 'fields' parameter"):
            test.validate_params(params={"to": "users"}, column_name="user_id")

    def test_validate_params_empty_to(self):
        """Test validation fails with empty 'to' parameter."""
        test = RelationshipsTest()

        with pytest.raises(ValueError, match="must be a non-empty string"):
            test.validate_params(params={"to": "", "field": "id"}, column_name="user_id")

    def test_validate_params_empty_field(self):
        """Test validation fails with empty 'field' parameter."""
        test = RelationshipsTest()

        with pytest.raises(ValueError, match="must be a non-empty string"):
            test.validate_params(params={"to": "users", "field": ""}, column_name="user_id")

    def test_validate_params_valid(self):
        """Test validation passes with valid parameters."""
        test = RelationshipsTest()

        # Should not raise
        test.validate_params(params={"to": "my_schema.users", "field": "id"}, column_name="user_id")

    def test_get_test_query_single_column(self):
        """Test query generation for single column."""
        test = RelationshipsTest()
        mock_adapter = Mock()
        mock_adapter.generate_relationships_test_query.return_value = "SELECT COUNT(*) FROM ..."

        test.get_test_query(
            mock_adapter,
            "my_schema.orders",
            column_name="user_id",
            params={"to": "my_schema.users", "field": "id"},
        )

        mock_adapter.generate_relationships_test_query.assert_called_once_with(
            "my_schema.orders", ["user_id"], "my_schema.users", ["id"]
        )

    def test_get_test_query_composite_key(self):
        """Test query generation for composite key."""
        test = RelationshipsTest()
        mock_adapter = Mock()
        mock_adapter.generate_relationships_test_query.return_value = "SELECT COUNT(*) FROM ..."

        test.get_test_query(
            mock_adapter,
            "my_schema.order_items",
            column_name="order_id",  # Primary column (for backward compat)
            params={
                "to": "my_schema.products",
                "fields": ["order_id", "product_id"],
                "source_fields": ["order_id", "product_id"],
            },
        )

        mock_adapter.generate_relationships_test_query.assert_called_once_with(
            "my_schema.order_items",
            ["order_id", "product_id"],
            "my_schema.products",
            ["order_id", "product_id"],
        )

    def test_execute_success(self):
        """Test execution when all relationships are valid."""
        test = RelationshipsTest()
        mock_adapter = Mock()
        mock_adapter.generate_relationships_test_query.return_value = "SELECT COUNT(*) FROM ..."
        mock_adapter.execute_query.return_value = [(0,)]  # No orphaned rows

        result = test.execute(
            mock_adapter,
            "my_schema.orders",
            column_name="user_id",
            params={"to": "my_schema.users", "field": "id"},
        )

        assert result.passed is True
        assert result.rows_returned == 0

    def test_execute_failure(self):
        """Test execution when orphaned rows found."""
        test = RelationshipsTest()
        mock_adapter = Mock()
        mock_adapter.generate_relationships_test_query.return_value = "SELECT COUNT(*) FROM ..."
        mock_adapter.execute_query.return_value = [(3,)]  # 3 orphaned rows

        result = test.execute(
            mock_adapter,
            "my_schema.orders",
            column_name="user_id",
            params={"to": "my_schema.users", "field": "id"},
        )

        assert result.passed is False
        assert result.rows_returned == 3

    def test_validate_params_both_field_and_fields(self):
        """Test validation fails when both 'field' and 'fields' are provided."""
        test = RelationshipsTest()

        with pytest.raises(ValueError, match="cannot use both 'field' and 'fields' parameters"):
            test.validate_params(
                params={"to": "users", "field": "id", "fields": ["id", "name"]},
                column_name="user_id",
            )

    def test_validate_params_composite_with_source_fields(self):
        """Test validation with composite key and source_fields."""
        test = RelationshipsTest()

        # Should not raise
        test.validate_params(
            params={
                "to": "my_schema.products",
                "fields": ["region_id", "country_id"],
                "source_fields": ["region_id", "country_id"],
            },
            column_name="region_id",
        )

    def test_validate_params_mismatched_source_fields_length(self):
        """Test validation fails when source_fields length doesn't match target."""
        test = RelationshipsTest()

        with pytest.raises(ValueError, match="must have the same length"):
            test.validate_params(
                params={
                    "to": "users",
                    "field": "id",
                    "source_fields": ["user_id", "other_id"],  # Length 2 vs 1
                },
                column_name="user_id",
            )
