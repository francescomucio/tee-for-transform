"""
Unit tests for PythonTest class.
"""

from unittest.mock import Mock

import pytest

from tee.testing.base import TestResult, TestSeverity
from tee.testing.python_test import PythonTest


class TestPythonTest:
    """Test cases for PythonTest class."""

    @pytest.fixture
    def python_test(self):
        """Create a PythonTest instance."""
        return PythonTest(
            name="my_test",
            sql="SELECT id FROM @table_name WHERE id IS NULL",
            severity=TestSeverity.ERROR,
            description="Test description",
            tags=["data-quality"],
        )

    @pytest.fixture
    def mock_adapter(self):
        """Create a mock adapter."""
        adapter = Mock()
        adapter.execute_query.return_value = []
        return adapter

    def test_init(self):
        """Test PythonTest initialization."""
        test = PythonTest(
            name="my_test",
            sql="SELECT 1",
            severity=TestSeverity.ERROR,
        )

        assert test.name == "my_test"
        assert test.sql == "SELECT 1"
        assert test.severity == TestSeverity.ERROR
        assert test.description is None
        assert test.tags == []

    def test_init_with_all_fields(self):
        """Test PythonTest initialization with all fields."""
        test = PythonTest(
            name="my_test",
            sql="SELECT 1",
            severity=TestSeverity.WARNING,
            description="Test description",
            tags=["tag1", "tag2"],
        )

        assert test.name == "my_test"
        assert test.sql == "SELECT 1"
        assert test.severity == TestSeverity.WARNING
        assert test.description == "Test description"
        assert test.tags == ["tag1", "tag2"]

    def test_validate_params(self, python_test):
        """Test validate_params (should pass for any params)."""
        # PythonTest accepts any parameters
        python_test.validate_params(params={"min_rows": 5})
        python_test.validate_params(params=None)
        python_test.validate_params(params={"min_rows": 5}, column_name="id")

    def test_get_test_query_basic(self, python_test, mock_adapter):
        """Test get_test_query with basic substitution."""
        query = python_test.get_test_query(
            adapter=mock_adapter,
            table_name="my_schema.my_table",
        )

        assert "my_schema.my_table" in query
        assert "@table_name" not in query
        assert "{{ table_name }}" not in query

    def test_get_test_query_with_column_name(self, python_test, mock_adapter):
        """Test get_test_query with column name substitution."""
        test = PythonTest(
            name="my_test",
            sql="SELECT @column_name FROM @table_name WHERE @column_name IS NULL",
        )

        query = test.get_test_query(
            adapter=mock_adapter,
            table_name="my_schema.my_table",
            column_name="id",
        )

        assert "my_schema.my_table" in query
        assert "id" in query
        assert "@column_name" not in query
        assert "@table_name" not in query

    def test_get_test_query_with_params(self, mock_adapter):
        """Test get_test_query with parameter substitution."""
        test = PythonTest(
            name="my_test",
            sql="SELECT 1 FROM @table_name WHERE count < @min_rows:10",
        )

        query = test.get_test_query(
            adapter=mock_adapter,
            table_name="my_schema.my_table",
            params={"min_rows": 5},
        )

        assert "my_schema.my_table" in query
        # Parameter should be substituted (exact substitution depends on implementation)
        assert "@min_rows" not in query or "5" in query

    def test_execute_passing_test(self, python_test, mock_adapter):
        """Test execute with passing test (0 rows returned)."""
        mock_adapter.execute_query.return_value = []

        result = python_test.execute(
            adapter=mock_adapter,
            table_name="my_schema.my_table",
        )

        assert isinstance(result, TestResult)
        assert result.passed is True
        assert result.test_name == "my_test"
        assert result.table_name == "my_schema.my_table"
        assert result.rows_returned == 0

    def test_execute_failing_test(self, python_test, mock_adapter):
        """Test execute with failing test (1+ rows returned)."""
        mock_adapter.execute_query.return_value = [(1,), (2,)]

        result = python_test.execute(
            adapter=mock_adapter,
            table_name="my_schema.my_table",
        )

        assert isinstance(result, TestResult)
        assert result.passed is False
        assert result.test_name == "my_test"
        assert result.table_name == "my_schema.my_table"
        assert result.rows_returned == 2
        assert "violation" in result.message.lower() or "failed" in result.message.lower()

    def test_execute_with_severity_override(self, python_test, mock_adapter):
        """Test execute with severity override."""
        mock_adapter.execute_query.return_value = [(1,)]

        result = python_test.execute(
            adapter=mock_adapter,
            table_name="my_schema.my_table",
            severity=TestSeverity.WARNING,
        )

        assert result.severity == TestSeverity.WARNING

    def test_execute_with_error(self, python_test, mock_adapter):
        """Test execute when query execution fails."""
        mock_adapter.execute_query.side_effect = Exception("Database error")

        result = python_test.execute(
            adapter=mock_adapter,
            table_name="my_schema.my_table",
        )

        assert isinstance(result, TestResult)
        assert result.passed is False
        assert result.error is not None
        assert "error" in result.message.lower()

    def test_execute_function_test_assertion_based(self, mock_adapter):
        """Test execute for function test (assertion-based pattern)."""
        test = PythonTest(
            name="my_test",
            sql="SELECT my_function(1, 2) = 3",
        )

        # Return True (test passes)
        mock_adapter.execute_query.return_value = [(True,)]

        result = test.execute(
            adapter=mock_adapter,
            function_name="my_schema.my_function",
        )

        assert result.passed is True
        assert result.function_name == "my_schema.my_function"

    def test_execute_function_test_expected_value(self, mock_adapter):
        """Test execute for function test (expected value pattern)."""
        test = PythonTest(
            name="my_test",
            sql="SELECT my_function(1, 2)",
        )

        # Return expected value
        mock_adapter.execute_query.return_value = [(3,)]

        result = test.execute(
            adapter=mock_adapter,
            function_name="my_schema.my_function",
            expected=3,
        )

        assert result.passed is True
        assert "expected 3" in result.message.lower()
