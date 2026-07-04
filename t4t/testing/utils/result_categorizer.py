"""
Result categorization utilities.

Extracts result categorization logic from TestExecutor.
"""

from t4t.testing.base import TestResult, TestSeverity


class ResultCategorizer:
    """Categorizes test results into errors and warnings."""

    @staticmethod
    def categorize_results(results: list[TestResult]) -> dict[str, list[str]]:
        """
        Categorize test results into errors and warnings.

        Args:
            results: List of test results

        Returns:
            Dictionary with 'errors' and 'warnings' lists
        """
        errors: list[str] = []
        warnings: list[str] = []

        for result in results:
            if result.severity == TestSeverity.WARNING:
                warnings.append(ResultCategorizer._format_warning(result))
            elif not result.passed and result.severity == TestSeverity.ERROR:
                errors.append(ResultCategorizer._format_error(result))

        return {"errors": errors, "warnings": warnings}

    @staticmethod
    def _format_warning(result: TestResult) -> str:
        """Format a warning message."""
        if result.function_name:
            return f"{result.test_name} on {result.function_name}: {result.message}"
        elif result.column_name:
            return (
                f"{result.test_name} on {result.table_name}.{result.column_name}: {result.message}"
            )
        else:
            return f"{result.test_name} on {result.table_name}: {result.message}"

    @staticmethod
    def _format_error(result: TestResult) -> str:
        """Format an error message."""
        if result.function_name:
            return f"{result.test_name} on {result.function_name}: {result.message}"
        elif result.column_name:
            return (
                f"{result.test_name} on {result.table_name}.{result.column_name}: {result.message}"
            )
        else:
            return f"{result.test_name} on {result.table_name}: {result.message}"
