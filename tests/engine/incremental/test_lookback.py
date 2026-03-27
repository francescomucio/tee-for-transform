"""
Test cases for lookback parsing and application.
"""

from tests.engine.incremental.test_executor_base import TestIncrementalExecutor


class TestLookbackParsing(TestIncrementalExecutor):
    """Test cases for _parse_lookback method."""

    def test_parse_minutes(self, executor):
        """Test parsing minutes."""
        result = executor._parse_lookback("30 minutes")
        assert result == "'30 minutes'"

    def test_parse_hours(self, executor):
        """Test parsing hours."""
        result = executor._parse_lookback("3 hours")
        assert result == "'3 hours'"

    def test_parse_days(self, executor):
        """Test parsing days."""
        result = executor._parse_lookback("7 days")
        assert result == "'7 days'"

    def test_parse_weeks(self, executor):
        """Test parsing weeks."""
        result = executor._parse_lookback("2 weeks")
        assert result == "'14 days'"

    def test_parse_months(self, executor):
        """Test parsing months."""
        result = executor._parse_lookback("1 month")
        assert result == "'30 days'"

    def test_parse_invalid_format(self, executor):
        """Test parsing invalid format."""
        result = executor._parse_lookback("invalid")
        assert result is None


class TestLookbackApplication(TestIncrementalExecutor):
    """Test cases for lookback application."""

    def test_apply_lookback_to_time_filter(self, executor, sample_append_config):
        """Test applying lookback to time filter."""
        time_filter = "created_at >= '2024-01-01'"

        result = executor._apply_lookback_to_time_filter(time_filter, sample_append_config)

        assert result == "created_at >= (CAST('2024-01-01' AS TIMESTAMP) - INTERVAL '7 days')"

    def test_apply_lookback_with_hours(self, executor):
        """Test applying lookback with hours."""
        config = {"filter_column": "created_at", "lookback": "3 hours"}
        time_filter = "created_at >= '2024-01-01'"

        result = executor._apply_lookback_to_time_filter(time_filter, config)

        assert result == "created_at >= (CAST('2024-01-01' AS TIMESTAMP) - INTERVAL '3 hours')"

    def test_apply_lookback_no_lookback(self, executor):
        """Test applying lookback when no lookback specified."""
        config = {"filter_column": "created_at"}
        time_filter = "created_at >= '2024-01-01'"

        result = executor._apply_lookback_to_time_filter(time_filter, config)

        assert result == "created_at >= '2024-01-01'"

    def test_apply_lookback_invalid_format(self, executor):
        """Test applying lookback with invalid format."""
        config = {"filter_column": "created_at", "lookback": "invalid"}
        time_filter = "created_at >= '2024-01-01'"

        result = executor._apply_lookback_to_time_filter(time_filter, config)

        assert result == "created_at >= '2024-01-01'"
