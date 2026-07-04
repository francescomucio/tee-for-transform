"""
Unit tests for TestExecutor.
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from t4t.testing.base import TestRegistry, TestSeverity
from t4t.testing.executor import TestExecutor
from t4t.testing.standard_tests import NotNullTest


class TestTestExecutor:
    """Test cases for TestExecutor."""

    @pytest.fixture
    def mock_adapter(self):
        """Create a mock adapter."""
        adapter = Mock()
        adapter.execute_query.return_value = [(0,)]
        return adapter

    @pytest.fixture
    def executor(self, mock_adapter):
        """Create a TestExecutor instance."""
        return TestExecutor(mock_adapter)

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_execute_tests_for_model_no_metadata(self, executor):
        """Test execution with no metadata."""
        results = executor.execute_tests_for_model("my_table", metadata=None)

        assert results == []

    def test_execute_tests_for_model_empty_metadata(self, executor):
        """Test execution with empty metadata."""
        results = executor.execute_tests_for_model("my_table", metadata={})

        assert results == []

    def test_execute_tests_for_model_column_level(self, executor, mock_adapter):
        """Test execution of column-level tests."""
        # Clear registry first
        TestRegistry.clear()
        # Register a test
        test = NotNullTest()
        TestRegistry.register(test)

        metadata = {"schema": [{"name": "id", "datatype": "number", "tests": ["not_null"]}]}

        mock_adapter.generate_not_null_test_query.return_value = (
            "SELECT COUNT(*) FROM table WHERE id IS NULL"
        )

        results = executor.execute_tests_for_model("my_table", metadata=metadata)

        assert len(results) == 1
        assert results[0].test_name == "not_null"
        assert results[0].column_name == "id"
        assert results[0].passed is True

    def test_execute_tests_for_model_table_level(self, executor, mock_adapter):
        """Test execution of table-level tests."""
        from t4t.testing.standard_tests import RowCountGreaterThanZeroTest

        # Clear registry first
        TestRegistry.clear()
        test = RowCountGreaterThanZeroTest()
        TestRegistry.register(test)

        metadata = {"tests": ["row_count_gt_0"]}

        mock_adapter.generate_row_count_gt_0_test_query.return_value = "SELECT COUNT(*) FROM table"
        mock_adapter.execute_query.return_value = [(3,)]

        results = executor.execute_tests_for_model("my_table", metadata=metadata)

        assert len(results) == 1
        assert results[0].test_name == "row_count_gt_0"
        assert results[0].column_name is None
        assert results[0].passed is True

    def test_execute_tests_for_model_unimplemented_test(self, executor):
        """Test execution with unimplemented test (should return warning)."""
        metadata = {"tests": ["nonexistent_test"]}

        results = executor.execute_tests_for_model("my_table", metadata=metadata)

        assert len(results) == 1
        assert results[0].test_name == "nonexistent_test"
        assert results[0].passed is True  # Passed by default for unimplemented
        assert results[0].severity == TestSeverity.WARNING
        assert "not implemented" in results[0].message.lower()

    def test_execute_all_tests(self, executor, mock_adapter):
        """Test execute_all_tests with multiple models."""
        from t4t.testing.standard_tests import NotNullTest, RowCountGreaterThanZeroTest

        # Clear registry first to ensure clean state
        TestRegistry.clear()

        # Register tests (these should already be registered, but we clear first)
        not_null_test = NotNullTest()
        row_count_test = RowCountGreaterThanZeroTest()
        TestRegistry.register(not_null_test)
        TestRegistry.register(row_count_test)

        parsed_models = {
            "my_schema.model1": {
                "model_metadata": {
                    "metadata": {
                        "schema": [{"name": "id", "datatype": "number", "tests": ["not_null"]}]
                    }
                }
            },
            "my_schema.model2": {"model_metadata": {"metadata": {"tests": ["row_count_gt_0"]}}},
        }

        execution_order = ["my_schema.model1", "my_schema.model2"]

        mock_adapter.generate_not_null_test_query.return_value = (
            "SELECT COUNT(*) FROM my_schema.model1 WHERE id IS NULL"
        )
        mock_adapter.generate_row_count_gt_0_test_query.return_value = (
            "SELECT COUNT(*) FROM my_schema.model2"
        )

        # Setup side_effect to return different values for different queries
        def execute_query_side_effect(query):
            if "row_count_gt_0" in query or "model2" in query:
                return [(3,)]  # row_count_gt_0 needs count > 0 to pass
            else:
                return [(0,)]  # not_null needs count == 0 to pass

        mock_adapter.execute_query.side_effect = execute_query_side_effect

        results = executor.execute_all_tests(parsed_models, execution_order)

        assert results["total"] == 2
        assert results["passed"] == 2
        assert results["failed"] == 0
        assert len(results["test_results"]) == 2

    def test_execute_all_tests_with_failures(self, executor, mock_adapter):
        """Test execute_all_tests with test failures."""
        from t4t.testing.standard_tests import NotNullTest

        # Clear registry first
        TestRegistry.clear()
        test = NotNullTest()
        TestRegistry.register(test)

        parsed_models = {
            "model1": {
                "model_metadata": {
                    "metadata": {
                        "schema": [{"name": "id", "datatype": "number", "tests": ["not_null"]}]
                    }
                }
            }
        }

        mock_adapter.generate_not_null_test_query.return_value = (
            "SELECT COUNT(*) FROM model1 WHERE id IS NULL"
        )
        mock_adapter.execute_query.return_value = [(5,)]  # 5 violations

        results = executor.execute_all_tests(parsed_models, ["model1"])

        assert results["total"] == 1
        assert results["passed"] == 0
        assert results["failed"] == 1
        assert len(results["errors"]) == 1

    def test_execute_all_tests_with_warnings(self, executor):
        """Test execute_all_tests with warnings (unimplemented tests)."""
        parsed_models = {
            "model1": {"model_metadata": {"metadata": {"tests": ["unimplemented_test"]}}}
        }

        results = executor.execute_all_tests(parsed_models, ["model1"])

        assert results["total"] == 1
        assert results["passed"] == 1  # Unimplemented tests count as passed
        assert results["failed"] == 0
        assert len(results["warnings"]) == 1

    def test_extract_metadata_from_model_data(self, executor):
        """Test metadata extraction from model data."""
        model_data = {
            "model_metadata": {"metadata": {"schema": [{"name": "id", "datatype": "number"}]}}
        }

        metadata = executor._extract_metadata(model_data)

        assert metadata is not None
        assert "schema" in metadata

    def test_extract_metadata_fallback(self, executor):
        """Test metadata extraction fallback."""
        model_data = {"metadata": {"schema": [{"name": "id", "datatype": "number"}]}}

        metadata = executor._extract_metadata(model_data)

        assert metadata is not None
        assert "schema" in metadata

    def test_extract_metadata_none(self, executor):
        """Test metadata extraction when no metadata exists."""
        model_data = {}

        metadata = executor._extract_metadata(model_data)

        assert metadata is None

    def test_executor_with_sql_tests_discovery(self, mock_adapter, temp_dir):
        """Test that TestExecutor discovers SQL tests from tests/ folder."""
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()

        # Create a SQL test file
        sql_file = tests_folder / "my_custom_test.sql"
        sql_file.write_text("SELECT 1 FROM {{ table_name }} WHERE id IS NULL")

        # Create executor with project folder (should trigger discovery)
        TestExecutor(mock_adapter, project_folder=str(temp_dir))

        # Verify SQL test was discovered and registered
        from t4t.testing.sql_test import SqlTest

        discovered_test = TestRegistry.get("my_custom_test")
        assert discovered_test is not None
        assert isinstance(discovered_test, SqlTest)

    def test_execute_sql_test_model_level(self, mock_adapter, temp_dir):
        """Test executing a SQL test at model level."""
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()

        # Create a SQL test file
        sql_file = tests_folder / "check_minimum_rows.sql"
        sql_file.write_text("""
SELECT 1 as violation
FROM {{ table_name }}
GROUP BY 1
HAVING COUNT(*) < 5
""")

        # Create executor with project folder
        executor = TestExecutor(mock_adapter, project_folder=str(temp_dir))

        # Mock adapter to return empty results (test passes)
        mock_adapter.execute_query.return_value = []

        metadata = {"tests": ["check_minimum_rows"]}

        results = executor.execute_tests_for_model("my_schema.my_table", metadata=metadata)

        assert len(results) == 1
        assert results[0].test_name == "check_minimum_rows"
        assert results[0].passed is True
        assert results[0].column_name is None

    def test_execute_sql_test_with_params(self, mock_adapter, temp_dir):
        """Test executing a SQL test with parameters."""
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()

        # Create a parameterized SQL test
        sql_file = tests_folder / "check_minimum_rows.sql"
        sql_file.write_text("""
SELECT 1 as violation
FROM {{ table_name }}
GROUP BY 1
HAVING COUNT(*) < {{ min_rows | default(10) }}
""")

        executor = TestExecutor(mock_adapter, project_folder=str(temp_dir))
        mock_adapter.execute_query.return_value = []

        metadata = {"tests": [{"name": "check_minimum_rows", "params": {"min_rows": 5}}]}

        results = executor.execute_tests_for_model("my_table", metadata=metadata)

        assert len(results) == 1
        assert results[0].test_name == "check_minimum_rows"
        assert results[0].passed is True

        # Verify query was called with substituted params
        assert mock_adapter.execute_query.called
        call_args = mock_adapter.execute_query.call_args[0][0]
        assert "my_table" in call_args

    def test_execute_sql_test_column_level(self, mock_adapter, temp_dir):
        """Test executing a SQL test at column level."""
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()

        # Create a column-level SQL test
        sql_file = tests_folder / "column_not_negative.sql"
        sql_file.write_text("""
SELECT {{ column_name }}
FROM {{ table_name }}
WHERE {{ column_name }} < 0
""")

        executor = TestExecutor(mock_adapter, project_folder=str(temp_dir))
        mock_adapter.execute_query.return_value = []  # No negative values = pass

        metadata = {
            "schema": [{"name": "amount", "datatype": "number", "tests": ["column_not_negative"]}]
        }

        results = executor.execute_tests_for_model("my_table", metadata=metadata)

        assert len(results) == 1
        assert results[0].test_name == "column_not_negative"
        assert results[0].column_name == "amount"
        assert results[0].passed is True

        # Verify query contains column name
        call_args = mock_adapter.execute_query.call_args[0][0]
        assert "amount" in call_args
        assert "my_table" in call_args

    def test_execute_sql_test_failure(self, mock_adapter, temp_dir):
        """Test executing a SQL test that fails (returns rows)."""
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()

        sql_file = tests_folder / "check_minimum_rows.sql"
        sql_file.write_text("SELECT 1 FROM {{ table_name }} WHERE COUNT(*) < 5")

        executor = TestExecutor(mock_adapter, project_folder=str(temp_dir))
        # Return 2 rows (test fails)
        mock_adapter.execute_query.return_value = [(1,), (2,)]

        metadata = {"tests": ["check_minimum_rows"]}

        results = executor.execute_tests_for_model("my_table", metadata=metadata)

        assert len(results) == 1
        assert results[0].test_name == "check_minimum_rows"
        assert results[0].passed is False
        assert results[0].rows_returned == 2
        assert "failed" in results[0].message.lower()

    def test_execute_all_tests_with_sql_tests(self, mock_adapter, temp_dir):
        """Test execute_all_tests with both standard and SQL tests."""
        from t4t.testing.standard_tests import NotNullTest

        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()

        # Create a SQL test
        sql_file = tests_folder / "my_custom_test.sql"
        sql_file.write_text("SELECT 1 FROM {{ table_name }}")

        # Clear registry and register standard test
        TestRegistry.clear()
        TestRegistry.register(NotNullTest())

        # Create executor (will discover SQL test)
        executor = TestExecutor(mock_adapter, project_folder=str(temp_dir))

        parsed_models = {
            "my_schema.model1": {
                "model_metadata": {
                    "metadata": {
                        "schema": [{"name": "id", "datatype": "number", "tests": ["not_null"]}],
                        "tests": ["my_custom_test"],
                    }
                }
            }
        }

        mock_adapter.generate_not_null_test_query.return_value = (
            "SELECT COUNT(*) FROM my_schema.model1 WHERE id IS NULL"
        )

        def execute_query_side_effect(query):
            if "not_null" in query or "IS NULL" in query:
                return [(0,)]  # Standard test passes
            else:
                return []  # SQL test passes

        mock_adapter.execute_query.side_effect = execute_query_side_effect

        results = executor.execute_all_tests(parsed_models, ["my_schema.model1"])

        assert results["total"] == 2  # One standard test, one SQL test
        assert results["passed"] == 2
        assert results["failed"] == 0
        assert len(results["test_results"]) == 2
