"""
Test cases for variable resolution methods.
"""

from tests.engine.incremental.test_executor_base import TestIncrementalExecutor


class TestVariableResolution(TestIncrementalExecutor):
    """Test cases for variable resolution methods."""

    def test_resolve_at_variable(self, executor):
        """Test resolving @variable syntax."""
        variables = {"start_date": "2024-01-01"}

        result = executor._resolve_variable("@start_date", variables)
        assert result == "2024-01-01"

    def test_resolve_brace_variable(self, executor):
        """Test resolving {{ variable }} syntax."""
        variables = {"start_date": "2024-01-01"}

        result = executor._resolve_variable("{{ start_date }}", variables)
        assert result == "2024-01-01"

    def test_resolve_variables_in_string(self, executor):
        """Test resolving multiple variables in a string."""
        variables = {"start_date": "2024-01-01", "end_date": "2024-01-31"}

        result = executor._resolve_variables_in_string(
            "created_at >= @start_date AND created_at <= @end_date", variables
        )
        assert result == "created_at >= 2024-01-01 AND created_at <= 2024-01-31"

    def test_resolve_variables_with_braces(self, executor):
        """Test resolving variables with {{ }} syntax."""
        variables = {"start_date": "2024-01-01"}

        result = executor._resolve_variables_in_string("created_at >= {{ start_date }}", variables)
        assert result == "created_at >= 2024-01-01"

    def test_missing_variable_fallback(self, executor):
        """Test fallback when variable is missing."""
        variables = {}

        result = executor._resolve_variables_in_string("created_at >= @missing_var", variables)
        assert result == "created_at >= @missing_var"
