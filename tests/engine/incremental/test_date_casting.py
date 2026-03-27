"""
Test cases for _add_date_casting method.
"""

from tests.engine.incremental.test_executor_base import TestIncrementalExecutor


class TestDateCasting(TestIncrementalExecutor):
    """Test cases for _add_date_casting method."""

    def test_add_date_casting_with_quotes(self, executor):
        """Test adding date casting with quoted dates."""
        where_condition = "created_at >= '2024-01-01'"

        result = executor._add_date_casting(where_condition)

        assert result == "created_at >= CAST('2024-01-01' AS DATE)"

    def test_add_date_casting_without_quotes(self, executor):
        """Test adding date casting without quotes."""
        where_condition = "created_at >= 2024-01-01"

        result = executor._add_date_casting(where_condition)

        assert result == "created_at >= CAST('2024-01-01' AS DATE)"

    def test_add_date_casting_multiple_dates(self, executor):
        """Test adding date casting with multiple dates."""
        where_condition = "created_at >= '2024-01-01' AND updated_at <= '2024-01-31'"

        result = executor._add_date_casting(where_condition)

        expected = (
            "created_at >= CAST('2024-01-01' AS DATE) AND updated_at <= CAST('2024-01-31' AS DATE)"
        )
        assert result == expected

    def test_add_date_casting_no_dates(self, executor):
        """Test adding date casting with no dates."""
        where_condition = "status = 'active'"

        result = executor._add_date_casting(where_condition)

        assert result == "status = 'active'"
