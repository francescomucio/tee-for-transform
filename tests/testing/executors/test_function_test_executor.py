"""
Unit tests for FunctionTestExecutor.
"""

import inspect
from unittest.mock import Mock, patch

import pytest

from tee.testing.base import TestRegistry, TestSeverity
from tee.testing.executors.function_test_executor import FunctionTestExecutor
from tee.testing.sql_test import SqlTest


class TestFunctionTestExecutor:
    """Test cases for FunctionTestExecutor."""

    @pytest.fixture
    def mock_adapter(self):
        """Create a mock adapter."""
        adapter = Mock()
        adapter.execute_query.return_value = [(True,)]
        return adapter

    @pytest.fixture
    def executor(self, mock_adapter):
        """Create a FunctionTestExecutor instance."""
        return FunctionTestExecutor(mock_adapter)

    @pytest.fixture(autouse=True)
    def clear_registry(self):
        """Clear test registry before and after each test."""
        TestRegistry.clear()
        yield
        TestRegistry.clear()

    def test_init(self, mock_adapter):
        """Test FunctionTestExecutor initialization."""
        executor = FunctionTestExecutor(mock_adapter)

        assert executor.adapter == mock_adapter
        assert executor._used_test_names == set()

    def test_execute_tests_for_function_no_metadata(self, executor):
        """Test execution with no metadata."""
        results = executor.execute_tests_for_function("my_function", metadata=None)

        assert results == []

    def test_execute_tests_for_function_empty_metadata(self, executor):
        """Test execution with empty metadata."""
        results = executor.execute_tests_for_function("my_function", metadata={})

        assert results == []

    def test_execute_tests_for_function_no_tests(self, executor):
        """Test execution with metadata but no tests."""
        metadata = {"description": "A function"}
        results = executor.execute_tests_for_function("my_function", metadata=metadata)

        assert results == []

    def test_execute_tests_for_function_unimplemented_test(self, executor):
        """Test execution with unimplemented test (should return warning)."""
        metadata = {"tests": ["nonexistent_test"]}

        results = executor.execute_tests_for_function("my_function", metadata=metadata)

        assert len(results) == 1
        assert results[0].test_name == "nonexistent_test"
        assert results[0].function_name == "my_function"
        assert results[0].passed is True
        assert results[0].severity == TestSeverity.WARNING
        assert "not implemented" in results[0].message.lower()

    def test_execute_tests_for_function_string_test_def(self, executor, mock_adapter, tmp_path):
        """Test execution with string test definition."""
        # Create a SQL test file
        test_file = tmp_path / "test_function_test.sql"
        test_file.write_text("SELECT @function_name(1, 2) = 3")

        sql_test = SqlTest(
            name="test_function_test",
            sql_file_path=test_file,
            project_folder=tmp_path,
        )
        TestRegistry.register(sql_test)

        metadata = {"tests": ["test_function_test"]}

        mock_adapter.execute_query.return_value = [(True,)]

        results = executor.execute_tests_for_function("my_schema.my_function", metadata=metadata)

        assert len(results) == 1
        assert results[0].test_name == "test_function_test"
        assert results[0].function_name == "my_schema.my_function"
        assert "test_function_test" in executor.get_used_test_names()

    def test_execute_tests_for_function_dict_test_def(self, executor, mock_adapter, tmp_path):
        """Test execution with dict test definition."""
        test_file = tmp_path / "test_function_test.sql"
        test_file.write_text("SELECT @function_name(@param1, @param2) = @expected")

        sql_test = SqlTest(
            name="test_function_test",
            sql_file_path=test_file,
            project_folder=tmp_path,
        )
        TestRegistry.register(sql_test)

        metadata = {
            "tests": [
                {
                    "name": "test_function_test",
                    "param1": 10,
                    "param2": 20,
                    "expected": 30,
                    "severity": "warning",
                }
            ]
        }

        mock_adapter.execute_query.return_value = [(True,)]

        results = executor.execute_tests_for_function("my_function", metadata=metadata)

        assert len(results) == 1
        assert results[0].test_name == "test_function_test"
        assert results[0].function_name == "my_function"

    def test_execute_tests_for_function_with_severity_override(
        self, executor, mock_adapter, tmp_path
    ):
        """Test execution with severity override."""
        test_file = tmp_path / "test_function_test.sql"
        test_file.write_text("SELECT @function_name(1) = 2")

        sql_test = SqlTest(
            name="test_function_test",
            sql_file_path=test_file,
            project_folder=tmp_path,
            severity=TestSeverity.ERROR,  # Default severity
        )
        TestRegistry.register(sql_test)

        metadata = {"tests": [{"name": "test_function_test", "severity": "warning"}]}
        severity_overrides = {}

        mock_adapter.execute_query.return_value = [(False,)]

        results = executor.execute_tests_for_function(
            "my_function", metadata=metadata, severity_overrides=severity_overrides
        )

        assert len(results) == 1
        assert results[0].severity == TestSeverity.WARNING

    def test_execute_tests_for_function_test_does_not_support_functions(
        self, executor, mock_adapter
    ):
        """Test execution with test that doesn't support function_name parameter."""
        # Create a mock test that doesn't support function_name
        mock_test = Mock()
        mock_test.execute = Mock()  # Standard test without function_name parameter
        mock_test.severity = TestSeverity.ERROR

        # Mock inspect.signature to return a signature without function_name
        sig = inspect.Signature(parameters=[])
        with patch("inspect.signature", return_value=sig):
            with patch.object(TestRegistry, "get", return_value=mock_test):
                metadata = {"tests": ["not_null"]}

                results = executor.execute_tests_for_function("my_function", metadata=metadata)

                assert len(results) == 0  # Should return None and not add to results

    def test_execute_tests_for_function_test_execution_error(
        self, executor, mock_adapter, tmp_path
    ):
        """Test execution when test raises an exception."""
        test_file = tmp_path / "test_function_test.sql"
        test_file.write_text("SELECT @function_name(1)")

        sql_test = SqlTest(
            name="test_function_test",
            sql_file_path=test_file,
            project_folder=tmp_path,
        )
        TestRegistry.register(sql_test)

        metadata = {"tests": ["test_function_test"]}

        # Make adapter raise an exception
        mock_adapter.execute_query.side_effect = Exception("Database error")

        results = executor.execute_tests_for_function("my_function", metadata=metadata)

        assert len(results) == 1
        assert results[0].passed is False
        assert results[0].error == "Database error"
        assert "Error executing SQL test" in results[0].message

    def test_execute_tests_for_function_multiple_tests(self, executor, mock_adapter, tmp_path):
        """Test execution with multiple tests."""
        # Create two test files
        test_file1 = tmp_path / "test1.sql"
        test_file1.write_text("SELECT @function_name(1) = 1")
        test_file2 = tmp_path / "test2.sql"
        test_file2.write_text("SELECT @function_name(2) = 2")

        sql_test1 = SqlTest(name="test1", sql_file_path=test_file1, project_folder=tmp_path)
        sql_test2 = SqlTest(name="test2", sql_file_path=test_file2, project_folder=tmp_path)

        TestRegistry.register(sql_test1)
        TestRegistry.register(sql_test2)

        metadata = {"tests": ["test1", "test2"]}

        mock_adapter.execute_query.return_value = [(True,)]

        results = executor.execute_tests_for_function("my_function", metadata=metadata)

        assert len(results) == 2
        assert {r.test_name for r in results} == {"test1", "test2"}
        assert executor.get_used_test_names() == {"test1", "test2"}

    def test_get_used_test_names(self, executor):
        """Test getting used test names."""
        assert executor.get_used_test_names() == set()

        # Simulate test execution
        executor._used_test_names.add("test1")
        executor._used_test_names.add("test2")

        assert executor.get_used_test_names() == {"test1", "test2"}

    def test_execute_tests_for_function_invalid_test_def(self, executor):
        """Test execution with invalid test definition."""
        metadata = {"tests": [123]}  # Invalid type

        results = executor.execute_tests_for_function("my_function", metadata=metadata)

        assert results == []

    def test_execute_tests_for_function_dict_missing_name(self, executor):
        """Test execution with dict test definition missing name."""
        metadata = {"tests": [{"param1": 10}]}  # Missing name

        results = executor.execute_tests_for_function("my_function", metadata=metadata)

        assert results == []
