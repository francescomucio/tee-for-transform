"""
Unit tests for SqlTest class.
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from t4t.testing.base import TestResult, TestSeverity
from t4t.testing.sql_test import SqlTest


class TestSqlTest:
    """Test cases for SqlTest class."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def sql_file(self, temp_dir):
        """Create a temporary SQL test file."""
        sql_file = temp_dir / "test_minimum_rows.sql"
        sql_file.write_text("""
SELECT 1 as violation
FROM {{ table_name }}
GROUP BY 1
HAVING COUNT(*) < 5
""")
        return sql_file

    @pytest.fixture
    def sql_test(self, sql_file, temp_dir):
        """Create a SqlTest instance."""
        return SqlTest(
            name="test_minimum_rows",
            sql_file_path=sql_file,
            project_folder=temp_dir,
            severity=TestSeverity.ERROR,
        )

    def test_init(self, sql_file, temp_dir):
        """Test SqlTest initialization."""
        test = SqlTest(name="my_test", sql_file_path=sql_file, project_folder=temp_dir)

        assert test.name == "my_test"
        assert test.sql_file_path == sql_file
        assert test.project_folder == temp_dir
        assert test.severity == TestSeverity.ERROR
        assert test._sql_content is None

    def test_init_with_severity(self, sql_file, temp_dir):
        """Test SqlTest initialization with custom severity."""
        test = SqlTest(
            name="my_test",
            sql_file_path=sql_file,
            project_folder=temp_dir,
            severity=TestSeverity.WARNING,
        )

        assert test.severity == TestSeverity.WARNING

    def test_load_sql_content(self, sql_test):
        """Test loading SQL content from file."""
        content = sql_test._load_sql_content()

        assert "SELECT 1 as violation" in content
        assert "{{ table_name }}" in content
        assert "HAVING COUNT(*) < 5" in content

    def test_load_sql_content_caching(self, sql_test):
        """Test that SQL content is cached after first load."""
        content1 = sql_test._load_sql_content()
        content2 = sql_test._load_sql_content()

        assert content1 == content2
        # Verify it was only read once (by checking that _sql_content is set)
        assert sql_test._sql_content is not None

    def test_load_sql_content_missing_file(self, temp_dir):
        """Test loading SQL from non-existent file."""
        missing_file = temp_dir / "missing.sql"
        test = SqlTest(name="missing", sql_file_path=missing_file, project_folder=temp_dir)

        with pytest.raises(ValueError, match="Failed to load SQL test file"):
            test._load_sql_content()

    def test_validate_params(self, sql_test):
        """Test parameter validation (SQL tests accept any parameters)."""
        # Should not raise any exceptions
        sql_test.validate_params()
        sql_test.validate_params(params={"min_rows": 10})
        sql_test.validate_params(params={"min_rows": 10}, column_name="amount")

    def test_get_test_query_basic(self, sql_test):
        """Test basic query generation with table_name substitution."""
        adapter = Mock()
        query = sql_test.get_test_query(adapter=adapter, table_name="my_schema.my_table")

        assert "my_schema.my_table" in query
        assert "{{ table_name }}" not in query
        assert "SELECT 1 as violation" in query

    def test_get_test_query_with_spaces(self, temp_dir):
        """Test query generation with spaces in Jinja syntax."""
        sql_file = temp_dir / "test.sql"
        sql_file.write_text("SELECT * FROM {{ table_name }} WHERE id = 1")

        test = SqlTest(name="test", sql_file_path=sql_file, project_folder=temp_dir)

        query = test.get_test_query(adapter=Mock(), table_name="my_table")
        assert "my_table" in query
        assert "{{ table_name }}" not in query

    def test_get_test_query_without_spaces(self, temp_dir):
        """Test query generation without spaces in Jinja syntax."""
        sql_file = temp_dir / "test.sql"
        sql_file.write_text("SELECT * FROM {{table_name}} WHERE id = 1")

        test = SqlTest(name="test", sql_file_path=sql_file, project_folder=temp_dir)

        query = test.get_test_query(adapter=Mock(), table_name="my_table")
        assert "my_table" in query
        assert "{{table_name}}" not in query

    def test_get_test_query_at_sign_syntax(self, temp_dir):
        """Test query generation with @variable syntax."""
        sql_file = temp_dir / "test.sql"
        sql_file.write_text("SELECT * FROM @table_name WHERE id = 1")

        test = SqlTest(name="test", sql_file_path=sql_file, project_folder=temp_dir)

        query = test.get_test_query(adapter=Mock(), table_name="my_table")
        assert "my_table" in query
        assert "@table_name" not in query

    def test_get_test_query_with_column_name(self, temp_dir):
        """Test query generation with column_name substitution."""
        sql_file = temp_dir / "test.sql"
        sql_file.write_text("""
SELECT {{ column_name }}
FROM {{ table_name }}
WHERE {{ column_name }} < 0
""")

        test = SqlTest(name="test", sql_file_path=sql_file, project_folder=temp_dir)

        query = test.get_test_query(adapter=Mock(), table_name="my_table", column_name="amount")

        assert "amount" in query
        assert "{{ column_name }}" not in query
        assert "my_table" in query

    def test_get_test_query_with_column_name_at_sign(self, temp_dir):
        """Test query generation with @column_name syntax."""
        sql_file = temp_dir / "test.sql"
        sql_file.write_text("SELECT @column_name FROM @table_name WHERE @column_name < 0")

        test = SqlTest(name="test", sql_file_path=sql_file, project_folder=temp_dir)

        query = test.get_test_query(adapter=Mock(), table_name="my_table", column_name="amount")

        assert "amount" in query
        assert "@column_name" not in query
        assert "my_table" in query

    def test_get_test_query_with_params(self, temp_dir):
        """Test query generation with parameter substitution."""
        sql_file = temp_dir / "test.sql"
        sql_file.write_text("""
SELECT 1 as violation
FROM {{ table_name }}
GROUP BY 1
HAVING COUNT(*) < {{ min_rows | default(10) }}
""")

        test = SqlTest(name="test", sql_file_path=sql_file, project_folder=temp_dir)

        query = test.get_test_query(adapter=Mock(), table_name="my_table", params={"min_rows": 5})

        assert "my_table" in query
        assert "5" in query
        assert "{{ min_rows" not in query

    def test_get_test_query_with_params_default(self, temp_dir):
        """Test query generation with default parameter value."""
        sql_file = temp_dir / "test.sql"
        sql_file.write_text("""
SELECT 1 as violation
FROM {{ table_name }}
GROUP BY 1
HAVING COUNT(*) < {{ min_rows | default(10) }}
""")

        test = SqlTest(name="test", sql_file_path=sql_file, project_folder=temp_dir)

        # Don't provide min_rows param, should use default
        query = test.get_test_query(adapter=Mock(), table_name="my_table")

        assert "my_table" in query
        assert "10" in query  # Should use default value

    def test_get_test_query_multiple_params(self, temp_dir):
        """Test query generation with multiple parameters."""
        sql_file = temp_dir / "test.sql"
        sql_file.write_text("""
SELECT *
FROM {{ table_name }}
WHERE status = {{ status | default('active') }}
  AND amount > {{ min_amount }}
""")

        test = SqlTest(name="test", sql_file_path=sql_file, project_folder=temp_dir)

        query = test.get_test_query(
            adapter=Mock(), table_name="my_table", params={"min_amount": 100}
        )

        assert "my_table" in query
        assert "100" in query
        assert "'active'" in query  # Default value should be used

    def test_execute_passing_test(self, sql_test):
        """Test executing a SQL test that passes (0 rows returned)."""
        adapter = Mock()
        adapter.execute_query.return_value = []  # No rows = pass

        result = sql_test.execute(adapter=adapter, table_name="my_schema.my_table")

        assert isinstance(result, TestResult)
        assert result.test_name == "test_minimum_rows"
        assert result.table_name == "my_schema.my_table"
        assert result.passed is True
        assert result.rows_returned == 0
        assert "passed" in result.message.lower()
        assert result.severity == TestSeverity.ERROR
        assert result.error is None

    def test_execute_failing_test(self, sql_test):
        """Test executing a SQL test that fails (1+ rows returned)."""
        adapter = Mock()
        adapter.execute_query.return_value = [(1,), (2,)]  # 2 rows = fail

        result = sql_test.execute(adapter=adapter, table_name="my_schema.my_table")

        assert isinstance(result, TestResult)
        assert result.test_name == "test_minimum_rows"
        assert result.table_name == "my_schema.my_table"
        assert result.passed is False
        assert result.rows_returned == 2
        assert "failed" in result.message.lower()
        assert "2 violation(s)" in result.message
        assert result.severity == TestSeverity.ERROR
        assert result.error is None

    def test_execute_with_severity_override(self, sql_test):
        """Test executing with severity override."""
        adapter = Mock()
        adapter.execute_query.return_value = []

        result = sql_test.execute(
            adapter=adapter, table_name="my_table", severity=TestSeverity.WARNING
        )

        assert result.severity == TestSeverity.WARNING

    def test_execute_with_column_name(self, sql_test):
        """Test executing with column_name parameter."""
        adapter = Mock()
        adapter.execute_query.return_value = []

        result = sql_test.execute(adapter=adapter, table_name="my_table", column_name="amount")

        assert result.column_name == "amount"

    def test_execute_with_params(self, sql_test):
        """Test executing with parameters."""
        adapter = Mock()
        adapter.execute_query.return_value = []

        sql_test.execute(adapter=adapter, table_name="my_table", params={"min_rows": 5})

        # Verify query was called with substituted params
        assert adapter.execute_query.called
        call_args = adapter.execute_query.call_args[0][0]
        assert "5" in call_args or "my_table" in call_args

    def test_execute_query_error(self, sql_test):
        """Test executing when query raises an error."""
        adapter = Mock()
        adapter.execute_query.side_effect = Exception("Database error")

        result = sql_test.execute(adapter=adapter, table_name="my_table")

        assert result.passed is False
        assert result.error == "Database error"
        assert "Error executing SQL test" in result.message

    def test_execute_non_list_results(self, sql_test):
        """Test executing when query returns non-list results."""
        adapter = Mock()
        adapter.execute_query.return_value = None  # Not a list

        result = sql_test.execute(adapter=adapter, table_name="my_table")

        # Should handle gracefully (treat as 0 rows)
        assert result.rows_returned == 0
        assert result.passed is True

    def test_execute_empty_list_results(self, sql_test):
        """Test executing when query returns empty list."""
        adapter = Mock()
        adapter.execute_query.return_value = []

        result = sql_test.execute(adapter=adapter, table_name="my_table")

        assert result.rows_returned == 0
        assert result.passed is True
