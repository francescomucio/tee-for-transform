"""
Unit tests for testing framework base classes and utilities.
"""

from unittest.mock import Mock

import pytest

from t4t.testing.base import StandardTest, TestRegistry, TestResult, TestSeverity


@pytest.fixture(autouse=True)
def restore_test_registry():
    """Automatically restore test registry after each test."""
    # Save registered tests before test

    TestRegistry.list_all()

    yield

    # Restore registry after test
    TestRegistry.clear()
    # Re-register standard tests
    from t4t.testing.standard_tests import (
        ACCEPTED_VALUES,
        NOT_NULL,
        ROW_COUNT_GT_0,
        UNIQUE,
    )

    TestRegistry.register(NOT_NULL)
    TestRegistry.register(UNIQUE)
    TestRegistry.register(ROW_COUNT_GT_0)
    TestRegistry.register(ACCEPTED_VALUES)


@pytest.fixture
def test_impl_class():
    """Fixture to create a TestImpl class for testing StandardTest functionality."""

    class TestImpl(StandardTest):
        def __init__(
            self, name="test", query="SELECT COUNT(*) FROM table", severity=TestSeverity.ERROR
        ):
            super().__init__(name, severity)
            self._query = query

        def get_test_query(
            self, adapter, table_name=None, column_name=None, function_name=None, params=None
        ):
            return self._query

        def validate_params(self, params=None, column_name=None):
            pass

    return TestImpl


class TestTestResult:
    """Test cases for TestResult dataclass."""

    def test_test_result_creation(self):
        """Test creating a TestResult with all fields."""
        result = TestResult(
            test_name="not_null",
            table_name="my_schema.my_table",
            column_name="id",
            passed=True,
            message="Test passed: not_null",
            severity=TestSeverity.ERROR,
            rows_returned=0,
        )

        assert result.test_name == "not_null"
        assert result.table_name == "my_schema.my_table"
        assert result.column_name == "id"
        assert result.passed is True
        assert result.message == "Test passed: not_null"
        assert result.severity == TestSeverity.ERROR
        assert result.rows_returned == 0
        assert result.error is None

    def test_test_result_defaults(self):
        """Test TestResult with default values."""
        result = TestResult(
            test_name="test", table_name="table", column_name=None, passed=True, message="message"
        )

        assert result.severity == TestSeverity.ERROR
        assert result.rows_returned is None
        assert result.error is None
        assert result.column_name is None

    def test_test_result_str_column(self):
        """Test string representation with column name."""
        result = TestResult(
            test_name="not_null",
            table_name="my_schema.my_table",
            column_name="id",
            passed=True,
            message="Test passed",
        )

        expected = "✅ PASS not_null on my_schema.my_table.id: Test passed"
        assert str(result) == expected

    def test_test_result_str_table(self):
        """Test string representation without column name."""
        result = TestResult(
            test_name="row_count_gt_0",
            table_name="my_schema.my_table",
            column_name=None,
            passed=True,
            message="Test passed",
        )

        expected = "✅ PASS row_count_gt_0 on my_schema.my_table: Test passed"
        assert str(result) == expected

    def test_test_result_str_failed(self):
        """Test string representation for failed test."""
        result = TestResult(
            test_name="not_null",
            table_name="my_schema.my_table",
            column_name="id",
            passed=False,
            message="Test failed: found 5 violations",
            severity=TestSeverity.ERROR,
        )

        expected = (
            "❌ FAIL (ERROR) not_null on my_schema.my_table.id: Test failed: found 5 violations"
        )
        assert str(result) == expected


class TestStandardTest:
    """Test cases for StandardTest base class."""

    def test_extract_row_count_list_tuple(self, test_impl_class):
        """Test extracting count from list of tuples (standard adapter result)."""
        test = test_impl_class("test", "SELECT COUNT(*) FROM table")
        results = [(5,)]  # Standard adapter format

        count = test._extract_row_count(results)
        assert count == 5

    def test_extract_row_count_empty_list(self, test_impl_class):
        """Test extracting count from empty list."""
        test = test_impl_class("test")
        results = []

        count = test._extract_row_count(results)
        assert count == 0

    def test_extract_row_count_multiple_rows(self, test_impl_class):
        """Test extracting count from multiple rows (should return 0 for invalid format)."""
        test = test_impl_class("test")
        results = [(1,), (2,)]  # Multiple rows - invalid for COUNT(*)

        count = test._extract_row_count(results)
        assert count == 0

    def test_check_passed_default(self, test_impl_class):
        """Test default check_passed logic (count == 0 means pass)."""
        test = test_impl_class("test")

        assert test.check_passed(0) is True  # No violations = pass
        assert test.check_passed(5) is False  # 5 violations = fail

    def test_format_message_passed(self, test_impl_class):
        """Test format_message for passed test."""
        test = test_impl_class("not_null")
        message = test.format_message(True, 0)

        assert message == "Test passed: not_null"

    def test_format_message_failed(self, test_impl_class):
        """Test format_message for failed test."""
        test = test_impl_class("not_null")
        message = test.format_message(False, 5)

        assert message == "Test failed: not_null found 5 violation(s)"

    def test_execute_success(self, test_impl_class):
        """Test execute method with successful test."""
        test = test_impl_class("not_null", "SELECT COUNT(*) FROM table WHERE column IS NULL")

        # Mock adapter
        mock_adapter = Mock()
        mock_adapter.execute_query.return_value = [(0,)]  # No violations

        result = test.execute(mock_adapter, "my_table", column_name="id")

        assert result.passed is True
        assert result.test_name == "not_null"
        assert result.table_name == "my_table"
        assert result.column_name == "id"
        assert result.rows_returned == 0
        assert result.severity == TestSeverity.ERROR
        assert "passed" in result.message.lower()

    def test_execute_failure(self, test_impl_class):
        """Test execute method with failed test."""
        test = test_impl_class("not_null", "SELECT COUNT(*) FROM table WHERE column IS NULL")

        # Mock adapter
        mock_adapter = Mock()
        mock_adapter.execute_query.return_value = [(3,)]  # 3 violations

        result = test.execute(mock_adapter, "my_table", column_name="id")

        assert result.passed is False
        assert result.rows_returned == 3
        assert "failed" in result.message.lower()
        assert "3 violation(s)" in result.message

    def test_execute_with_exception(self, test_impl_class):
        """Test execute method when query execution fails."""
        test = test_impl_class("not_null")

        # Mock adapter that raises exception
        mock_adapter = Mock()
        mock_adapter.execute_query.side_effect = Exception("Database error")

        result = test.execute(mock_adapter, "my_table", column_name="id")

        assert result.passed is False
        assert result.error == "Database error"
        assert "error" in result.message.lower()

    def test_execute_with_severity_override(self, test_impl_class):
        """Test execute method with severity override."""
        test = test_impl_class("not_null")

        mock_adapter = Mock()
        mock_adapter.execute_query.return_value = [(0,)]

        result = test.execute(mock_adapter, "my_table", severity=TestSeverity.WARNING)

        assert result.severity == TestSeverity.WARNING


class TestTestRegistry:
    """Test cases for TestRegistry."""

    def test_register_and_get(self, test_impl_class):
        """Test registering and retrieving a test."""
        test = test_impl_class("custom_test")

        # Clear registry first
        TestRegistry.clear()

        TestRegistry.register(test)
        retrieved = TestRegistry.get("custom_test")

        assert retrieved is not None
        assert retrieved.name == "custom_test"
        assert retrieved is test

    def test_get_nonexistent(self):
        """Test retrieving a test that doesn't exist."""
        TestRegistry.clear()

        result = TestRegistry.get("nonexistent_test")

        assert result is None

    def test_list_all(self, test_impl_class):
        """Test listing all registered tests."""
        TestRegistry.clear()

        test1 = test_impl_class("test1")
        test2 = test_impl_class("test2")

        TestRegistry.register(test1)
        TestRegistry.register(test2)

        all_tests = TestRegistry.list_all()

        assert "test1" in all_tests
        assert "test2" in all_tests
        assert len(all_tests) == 2

    def test_clear(self, test_impl_class):
        """Test clearing the registry."""
        test = test_impl_class("test")

        TestRegistry.register(test)
        assert TestRegistry.get("test") is not None

        TestRegistry.clear()
        assert TestRegistry.get("test") is None
        assert len(TestRegistry.list_all()) == 0
