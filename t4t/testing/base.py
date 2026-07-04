"""
Base classes and types for the testing framework.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any


class TestSeverity(Enum):
    """Severity level for test failures."""

    __test__ = False  # Tell pytest this is not a test class

    ERROR = "error"
    WARNING = "warning"


@dataclass
class TestResult:
    """Result of a test execution."""

    __test__ = False  # Tell pytest this is not a test class

    test_name: str
    table_name: str | None = None  # For model tests
    column_name: str | None = None
    function_name: str | None = None  # For function tests
    passed: bool = False
    message: str = ""
    severity: TestSeverity = TestSeverity.ERROR
    rows_returned: int | None = None
    error: str | None = None

    def __str__(self) -> str:
        status = "✅ PASS" if self.passed else f"❌ FAIL ({self.severity.value.upper()})"
        if self.function_name:
            location = self.function_name
        elif self.column_name:
            location = (
                f"{self.table_name}.{self.column_name}" if self.table_name else self.column_name
            )
        else:
            location = self.table_name or "unknown"
        return f"{status} {self.test_name} on {location}: {self.message}"


class StandardTest(ABC):
    """Base class for standard tests."""

    def __init__(self, name: str, severity: TestSeverity = TestSeverity.ERROR):
        """
        Initialize a standard test.

        Args:
            name: Test name identifier
            severity: Default severity level for test failures
        """
        self.name = name
        self.severity = severity

    @abstractmethod
    def get_test_query(
        self,
        adapter,
        table_name: str | None = None,
        column_name: str | None = None,
        function_name: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> str:
        """
        Generate the SQL query for this test using the adapter.

        For model tests: The query should return rows when the test fails (like dbt).
        Zero rows = test passes.

        For function tests: The query can return boolean (assertion-based) or a value (expected value pattern).

        Args:
            adapter: Database adapter instance (for database-specific SQL generation)
            table_name: Fully qualified table name (for model tests)
            column_name: Column name if this is a column-level test (for model tests)
            function_name: Fully qualified function name (for function tests)
            params: Optional parameters for the test

        Returns:
            SQL query string
        """
        pass

    @abstractmethod
    def validate_params(
        self, params: dict[str, Any] | None = None, column_name: str | None = None
    ) -> None:
        """
        Validate test parameters.

        Args:
            params: Test parameters to validate
            column_name: Column name if this is a column-level test (for validation context)

        Raises:
            ValueError: If parameters are invalid
        """
        pass

    def _validate_model_level_only(self, column_name: str | None) -> None:
        """
        Validate that a model-level test is not applied to a column.

        Args:
            column_name: Column name (should be None for model-level tests)

        Raises:
            ValueError: If column_name is provided
        """
        if column_name:
            raise ValueError(
                f"{self.name} test is a model-level test and cannot be applied to a column"
            )

    def _validate_unknown_params(self, params: dict[str, Any] | None, allowed_params: set) -> None:
        """
        Validate that no unknown parameters are provided.

        Args:
            params: Test parameters to validate
            allowed_params: Set of allowed parameter names

        Raises:
            ValueError: If unknown parameters are found
        """
        if params:
            unknown_params = set(params.keys()) - allowed_params
            if unknown_params:
                raise ValueError(f"Unknown parameters for {self.name} test: {unknown_params}")

    def _extract_row_count(self, results: Any) -> int:
        """
        Extract row count value from query results.

        All adapters return list[tuple] from fetchall(). For COUNT(*) queries,
        this is always [(count,)] - a list with one tuple containing one integer.
        The count represents rows (either violating rows or total rows).

        Args:
            results: Raw query results from adapter.execute_query()

        Returns:
            Extracted row count value (0 if unable to extract)
        """
        if isinstance(results, list) and len(results) == 1:
            # COUNT(*) returns [(count,)] - list with one tuple
            return int(results[0][0])

        return 0

    def check_passed(self, count: int) -> bool:
        """
        Determine if test passed based on count value.

        Default: test passes if count == 0 (no violations).
        Override this method for tests with different logic (e.g., row_count_gt_0).

        Args:
            count: The count value from the query

        Returns:
            True if test passed, False otherwise
        """
        return count == 0

    def format_message(self, passed: bool, count: int) -> str:
        """
        Format test result message.

        Args:
            passed: Whether the test passed
            count: The count value from the query

        Returns:
            Human-readable message
        """
        if passed:
            return f"Test passed: {self.name}"
        else:
            return f"Test failed: {self.name} found {count} violation(s)"

    def execute(
        self,
        adapter,
        table_name: str | None = None,
        column_name: str | None = None,
        function_name: str | None = None,
        params: dict[str, Any] | None = None,
        severity: TestSeverity | None = None,
    ) -> TestResult:
        """
        Execute the test against a table or function.

        Args:
            adapter: Database adapter instance
            table_name: Fully qualified table name (for model tests)
            column_name: Column name if this is a column-level test (for model tests)
            function_name: Fully qualified function name (for function tests)
            params: Optional parameters for the test
            severity: Override severity level (uses test default if None)

        Returns:
            TestResult object
        """
        # Validate parameters
        self.validate_params(params, column_name)

        # Use provided severity or test default
        test_severity = severity or self.severity

        try:
            # Get test query (adapter generates database-specific SQL)
            query = self.get_test_query(adapter, table_name, column_name, function_name, params)

            # Execute query
            results = adapter.execute_query(query)

            # Extract row count from results (all tests return COUNT(*) queries)
            count = self._extract_row_count(results)

            # Check if test passed using test-specific logic
            passed = self.check_passed(count)

            # Format message
            message = self.format_message(passed, count)

            return TestResult(
                test_name=self.name,
                table_name=table_name,
                column_name=column_name,
                passed=passed,
                message=message,
                severity=test_severity,
                rows_returned=count,
            )

        except Exception as e:
            error_msg = f"Error executing test {self.name}: {str(e)}"
            return TestResult(
                test_name=self.name,
                table_name=table_name,
                column_name=column_name,
                passed=False,
                message=error_msg,
                severity=test_severity,
                error=str(e),
            )


class TestRegistry:
    """Registry for standard tests."""

    _tests: dict[str, StandardTest] = {}

    @classmethod
    def register(cls, test: StandardTest) -> None:
        """
        Register a standard test.

        Args:
            test: StandardTest instance to register
        """
        cls._tests[test.name] = test

    @classmethod
    def get(cls, name: str) -> StandardTest | None:
        """
        Get a registered test by name.

        Args:
            name: Test name

        Returns:
            StandardTest instance or None if not found
        """
        return cls._tests.get(name)

    @classmethod
    def list_all(cls) -> list[str]:
        """
        List all registered test names.

        Returns:
            List of test names
        """
        return list(cls._tests.keys())

    @classmethod
    def clear(cls) -> None:
        """
        Clear all registered tests (mainly for testing).
        """
        cls._tests.clear()
