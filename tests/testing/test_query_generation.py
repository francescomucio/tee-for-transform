"""
Unit tests for test query generation in adapters.
"""

import pytest

from t4t.adapters.base.testing import TestQueryGenerator


class TestQueryGeneratorImpl(TestQueryGenerator):
    """Concrete implementation of TestQueryGenerator for testing."""

    pass


class TestQueryGeneration:
    """Test cases for query generation methods."""

    @pytest.fixture
    def generator(self):
        """Create a TestQueryGenerator instance."""
        return TestQueryGeneratorImpl()

    def test_generate_not_null_test_query(self, generator):
        """Test not_null query generation."""
        query = generator.generate_not_null_test_query("my_schema.my_table", "id")

        assert "SELECT COUNT(*)" in query
        assert "my_schema.my_table" in query
        assert "id IS NULL" in query

    def test_generate_unique_test_query_single_column(self, generator):
        """Test unique query generation for single column."""
        query = generator.generate_unique_test_query("my_table", ["id"])

        assert "SELECT COUNT(*)" in query
        assert "my_table" in query
        assert "id" in query
        assert "GROUP BY" in query
        assert "HAVING COUNT(*)" in query

    def test_generate_unique_test_query_multiple_columns(self, generator):
        """Test unique query generation for multiple columns."""
        query = generator.generate_unique_test_query("my_table", ["col1", "col2"])

        assert "SELECT COUNT(*)" in query
        assert "col1" in query
        assert "col2" in query
        assert "GROUP BY" in query

    def test_generate_unique_test_query_with_columns(self, generator):
        """Test unique query generation with explicit columns."""
        query = generator.generate_unique_test_query("my_table", ["id", "name"])

        assert "SELECT COUNT(*)" in query
        assert "id" in query
        assert "name" in query
        assert "GROUP BY" in query
        assert "HAVING COUNT(*)" in query

    def test_generate_unique_test_query_without_columns(self, generator):
        """Test unique query generation without explicit columns (entire row uniqueness)."""
        query = generator.generate_unique_test_query("my_table", None)

        assert "SELECT COUNT(*)" in query
        assert "my_table" in query
        assert "GROUP BY *" in query  # Default uses GROUP BY * for all columns

    def test_generate_row_count_gt_0_test_query(self, generator):
        """Test row_count_gt_0 query generation."""
        query = generator.generate_row_count_gt_0_test_query("my_table")

        assert query == "SELECT COUNT(*) FROM my_table"

    def test_generate_accepted_values_test_query_strings(self, generator):
        """Test accepted_values query generation with string values."""
        query = generator.generate_accepted_values_test_query(
            "my_table", "status", ["active", "inactive", "pending"]
        )

        assert "SELECT COUNT(*)" in query
        assert "my_table" in query
        assert "status NOT IN" in query
        assert "'active'" in query
        assert "'inactive'" in query
        assert "'pending'" in query

    def test_generate_accepted_values_test_query_numbers(self, generator):
        """Test accepted_values query generation with numeric values."""
        query = generator.generate_accepted_values_test_query("my_table", "id", [1, 2, 3])

        assert "SELECT COUNT(*)" in query
        assert "id NOT IN" in query
        assert "1" in query
        assert "2" in query
        assert "3" in query
        # Numbers should not be quoted
        assert "'1'" not in query

    def test_generate_accepted_values_test_query_mixed_types(self, generator):
        """Test accepted_values query generation with mixed types."""
        query = generator.generate_accepted_values_test_query("my_table", "value", ["string", 123])

        assert "SELECT COUNT(*)" in query
        assert "'string'" in query
        assert "123" in query
        # 123 should not be quoted (it's a number)
        assert "'123'" not in query

    def test_generate_accepted_values_test_query_escaped_quotes(self, generator):
        """Test accepted_values query generation with strings containing quotes."""
        query = generator.generate_accepted_values_test_query(
            "my_table", "name", ["O'Brien", "Smith"]
        )

        # Single quotes should be escaped (doubled)
        assert "O''Brien" in query or "O'\\'Brien" in query
        assert "'Smith'" in query

    def test_generate_accepted_values_test_query_empty_list(self, generator):
        """Test accepted_values query generation fails with empty list."""
        with pytest.raises(ValueError, match="at least one value"):
            generator.generate_accepted_values_test_query("my_table", "col", [])

    def test_generate_accepted_values_test_query_with_null(self, generator):
        """Test accepted_values query generation with NULL value."""
        query = generator.generate_accepted_values_test_query(
            "my_table", "status", ["active", None, "inactive"]
        )

        assert "NULL" in query
        assert "'active'" in query
        assert "'inactive'" in query

    def test_generate_relationships_test_query_single_column(self, generator):
        """Test relationships query generation for single column."""
        query = generator.generate_relationships_test_query(
            "my_schema.orders", ["user_id"], "my_schema.users", ["id"]
        )

        assert "SELECT COUNT(*)" in query
        assert "my_schema.orders" in query
        assert "my_schema.users" in query
        assert "user_id" in query
        assert "id" in query
        assert "LEFT JOIN" in query
        assert "WHERE target.id IS NULL" in query
        assert "source.user_id = target.id" in query

    def test_generate_relationships_test_query_composite_key(self, generator):
        """Test relationships query generation for composite key."""
        query = generator.generate_relationships_test_query(
            "my_schema.order_items",
            ["order_id", "product_id"],
            "my_schema.products",
            ["order_id", "product_id"],
        )

        assert "SELECT COUNT(*)" in query
        assert "my_schema.order_items" in query
        assert "my_schema.products" in query
        assert "LEFT JOIN" in query
        assert "source.order_id = target.order_id" in query
        assert "source.product_id = target.product_id" in query
        assert "WHERE" in query
        assert "target.order_id IS NULL" in query or "target.product_id IS NULL" in query

    def test_generate_relationships_test_query_mismatched_lengths(self, generator):
        """Test relationships query generation fails with mismatched column counts."""
        with pytest.raises(ValueError, match="must have the same length"):
            generator.generate_relationships_test_query(
                "my_schema.orders",
                ["user_id"],
                "my_schema.users",
                ["id", "name"],  # Length 2 vs 1
            )
