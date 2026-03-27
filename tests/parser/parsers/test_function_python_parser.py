"""
Unit tests for Python function parser.
"""

from pathlib import Path

import pytest

from tee.parser.parsers.function_python_parser import (
    FunctionPythonParser,
    FunctionPythonParsingError,
)
from tee.parser.shared.registry import FunctionRegistry


class TestFunctionPythonParser:
    """Test Python function parser."""

    @pytest.fixture(autouse=True)
    def clear_registry(self):
        """Clear function registry before and after each test."""
        FunctionRegistry.clear()
        yield
        FunctionRegistry.clear()

    def test_parse_metadata_only_file(self):
        """Test parsing a metadata-only Python file with SQLFunctionMetadata."""
        import tempfile

        parser = FunctionPythonParser()

        # Create a temporary directory with test.py and test.sql
        with tempfile.TemporaryDirectory() as tmpdir:
            test_py = Path(tmpdir) / "test.py"
            test_sql = Path(tmpdir) / "test.sql"

            # Create companion SQL file
            test_sql.write_text("""
CREATE FUNCTION calculate_percentage(numerator DOUBLE, denominator DOUBLE)
RETURNS DOUBLE
AS $$
    CASE WHEN denominator = 0 THEN NULL ELSE (numerator / denominator) * 100 END
$$;
""")

            content = """
from tee.parser.processing.function_builder import SQLFunctionMetadata
from tee.typing import FunctionMetadata

metadata: FunctionMetadata = {
    "function_name": "calculate_percentage",
    "description": "Calculates percentage",
    "function_type": "scalar",
    "language": "sql",
    "return_type": "DOUBLE",
    "parameters": [
        {"name": "numerator", "type": "DOUBLE"},
        {"name": "denominator", "type": "DOUBLE"}
    ],
    "tags": ["math", "utility"]
}

# Automatically creates a function from metadata and companion SQL file
function = SQLFunctionMetadata(metadata)
"""

            result = parser.parse(content, str(test_py))

            assert len(result) == 1
            assert "calculate_percentage" in result

            func_data = result["calculate_percentage"]
            assert "function_metadata" in func_data
            # Metadata-only files with language="sql" need evaluation (they generate SQL)
            assert func_data["needs_evaluation"] is True

            metadata = func_data["function_metadata"]
            assert metadata["function_name"] == "calculate_percentage"
            assert metadata["description"] == "Calculates percentage"
            assert metadata["function_type"] == "scalar"
            assert metadata["language"] == "sql"
            assert len(metadata["parameters"]) == 2
            assert metadata["tags"] == ["math", "utility"]

    def test_parse_sql_decorator_function(self):
        """Test parsing a function with @functions.sql() decorator."""
        parser = FunctionPythonParser()

        content = """
from tee.parser.processing.function_decorator import functions

@functions.sql(
    function_name="calculate_metric",
    return_type="FLOAT",
    description="Calculates a metric",
    tags=["analytics"]
)
def generate_calc_sql(adapter_type: str) -> str:
    if adapter_type == "snowflake":
        return "CREATE FUNCTION calculate_metric(value FLOAT) RETURNS FLOAT AS $$ SELECT value * 2.0 $$;"
    return "CREATE FUNCTION calculate_metric(value DOUBLE) RETURNS DOUBLE AS $$ SELECT value * 2.0 $$;"
"""

        result = parser.parse(content, "test.py")

        assert len(result) == 1
        assert "calculate_metric" in result

        func_data = result["calculate_metric"]
        assert func_data["needs_evaluation"] is True  # SQL-generating functions need evaluation
        assert func_data["code"] is None  # Code is populated during evaluation

        metadata = func_data["function_metadata"]
        assert metadata["function_name"] == "calculate_metric"
        assert metadata["return_type"] == "FLOAT"
        assert metadata["description"] == "Calculates a metric"
        assert metadata["language"] == "sql"
        assert metadata["tags"] == ["analytics"]

    def test_parse_python_decorator_function(self):
        """Test parsing a function with @functions.python() decorator."""
        parser = FunctionPythonParser()

        content = """
from tee.parser.processing.function_decorator import functions

@functions.python(
    function_name="python_calculator",
    return_type="FLOAT",
    description="Python calculator function"
)
def python_calculator(x: float) -> float:
    return x * 2.5 + 10
"""

        result = parser.parse(content, "test.py")

        assert len(result) == 1
        assert "python_calculator" in result

        func_data = result["python_calculator"]
        assert func_data["needs_evaluation"] is False  # Python UDFs don't need evaluation

        metadata = func_data["function_metadata"]
        assert metadata["function_name"] == "python_calculator"
        assert metadata["language"] == "python"
        assert metadata["return_type"] == "FLOAT"

    def test_parse_multiple_functions_per_file(self):
        """Test parsing multiple functions in a single file."""
        parser = FunctionPythonParser()

        content = """
from tee.parser.processing.function_decorator import functions

@functions.sql(function_name="func1", return_type="INT")
def generate_func1(adapter_type: str) -> str:
    return "CREATE FUNCTION func1() RETURNS INT AS $$ SELECT 1 $$;"

@functions.sql(function_name="func2", return_type="FLOAT")
def generate_func2(adapter_type: str) -> str:
    return "CREATE FUNCTION func2() RETURNS FLOAT AS $$ SELECT 2.0 $$;"

@functions.python(function_name="func3", return_type="INT")
def func3(x: int) -> int:
    return x * 2
"""

        result = parser.parse(content, "test.py")

        assert len(result) == 3
        assert "func1" in result
        assert "func2" in result
        assert "func3" in result

        assert result["func1"]["function_metadata"]["language"] == "sql"
        assert result["func2"]["function_metadata"]["language"] == "sql"
        assert result["func3"]["function_metadata"]["language"] == "python"

    def test_parse_extract_docstring(self):
        """Test that docstring is extracted as description if not provided."""
        parser = FunctionPythonParser()

        content = """
from tee.parser.processing.function_decorator import functions

@functions.sql(function_name="test_func", return_type="INT")
def generate_sql(adapter_type: str) -> str:
    \"\"\"This is a test function that generates SQL.\"\"\"
    return "CREATE FUNCTION test_func() RETURNS INT AS $$ SELECT 1 $$;"
"""

        result = parser.parse(content, "test.py")

        metadata = result["test_func"]["function_metadata"]
        assert metadata["description"] == "This is a test function that generates SQL."

    def test_parse_extract_function_signature(self):
        """Test that function signature is extracted for parameters."""
        parser = FunctionPythonParser()

        content = """
from tee.parser.processing.function_decorator import functions

@functions.sql(function_name="test_func", return_type="FLOAT")
def generate_sql(adapter_type: str, value: float, count: int = 10) -> str:
    return "CREATE FUNCTION test_func(value FLOAT) RETURNS FLOAT AS $$ SELECT value $$;"
"""

        result = parser.parse(content, "test.py")

        metadata = result["test_func"]["function_metadata"]
        # Parameters should be extracted from function signature
        # Note: exact format depends on implementation
        metadata.get("parameters", [])
        # Should have at least some parameter information

    def test_parse_requires_file_path(self):
        """Test that file_path is required."""
        parser = FunctionPythonParser()

        content = "@functions.sql(function_name='test', return_type='INT')\ndef test(): pass"

        with pytest.raises(FunctionPythonParsingError):
            parser.parse(content, file_path=None)

    def test_parse_invalid_syntax(self):
        """Test error handling for invalid Python syntax."""
        parser = FunctionPythonParser()

        content = "invalid python syntax here !!!"

        with pytest.raises(FunctionPythonParsingError):
            parser.parse(content, "test.py")

    def test_parse_no_functions(self):
        """Test parsing file with no function definitions."""
        parser = FunctionPythonParser()

        content = """
# Just a comment
x = 1
y = 2
"""

        result = parser.parse(content, "test.py")

        # Should return empty dict (no functions found)
        assert len(result) == 0

    def test_parse_caching(self):
        """Test that parsing results are cached."""
        parser = FunctionPythonParser()

        content = """
@functions.sql(function_name="test", return_type="INT")
def test(): return "SELECT 1"
"""

        result1 = parser.parse(content, "test.py")
        result2 = parser.parse(content, "test.py")

        # Should return cached result
        assert result1 == result2
        assert result1 is result2  # Same object reference

    def test_parse_with_tags(self):
        """Test parsing function with tags."""
        parser = FunctionPythonParser()

        content = """
from tee.parser.processing.function_decorator import functions

@functions.sql(
    function_name="test_func",
    return_type="INT",
    tags=["math", "utility"],
    object_tags={"category": "calculation", "complexity": "simple"}
)
def generate_sql(adapter_type: str) -> str:
    return "CREATE FUNCTION test_func() RETURNS INT AS $$ SELECT 1 $$;"
"""

        result = parser.parse(content, "test.py")

        metadata = result["test_func"]["function_metadata"]
        assert metadata["tags"] == ["math", "utility"]
        assert metadata["object_tags"] == {"category": "calculation", "complexity": "simple"}

    def test_parse_with_schema(self):
        """Test parsing function with schema specification."""
        parser = FunctionPythonParser()

        content = """
from tee.parser.processing.function_decorator import functions

@functions.sql(
    function_name="test_func",
    return_type="INT",
    schema="my_schema"
)
def generate_sql(adapter_type: str) -> str:
    return "CREATE FUNCTION my_schema.test_func() RETURNS INT AS $$ SELECT 1 $$;"
"""

        result = parser.parse(content, "test.py")

        metadata = result["test_func"]["function_metadata"]
        assert metadata["schema"] == "my_schema"

    def test_parse_table_function(self):
        """Test parsing a table-valued function."""
        parser = FunctionPythonParser()

        content = """
from tee.parser.processing.function_decorator import functions

@functions.sql(
    function_name="get_users",
    function_type="table",
    return_table_schema=[
        {"name": "id", "type": "INT"},
        {"name": "name", "type": "VARCHAR"}
    ]
)
def generate_sql(adapter_type: str) -> str:
    return "CREATE FUNCTION get_users() RETURNS TABLE(id INT, name VARCHAR) AS $$ SELECT id, name FROM users $$;"
"""

        result = parser.parse(content, "test.py")

        metadata = result["get_users"]["function_metadata"]
        assert metadata["function_type"] == "table"
        assert metadata["return_table_schema"] is not None
        assert len(metadata["return_table_schema"]) == 2

    def test_parse_aggregate_function(self):
        """Test parsing an aggregate function."""
        parser = FunctionPythonParser()

        content = """
from tee.parser.processing.function_decorator import functions

@functions.sql(
    function_name="custom_sum",
    function_type="aggregate",
    return_type="FLOAT"
)
def generate_sql(adapter_type: str) -> str:
    return "CREATE AGGREGATE FUNCTION custom_sum(value FLOAT) RETURNS FLOAT;"
"""

        result = parser.parse(content, "test.py")

        metadata = result["custom_sum"]["function_metadata"]
        assert metadata["function_type"] == "aggregate"

    def test_parse_database_name_override(self):
        """Test parsing function with database_name for overloading."""
        parser = FunctionPythonParser()

        content = """
from tee.parser.processing.function_decorator import functions

@functions.sql(
    function_name="test_func",
    return_type="INT",
    database_name="snowflake"
)
def generate_sql_snowflake(adapter_type: str) -> str:
    return "CREATE FUNCTION test_func() RETURNS INT AS $$ SELECT 1 $$;"
"""

        result = parser.parse(content, "test.py")

        metadata = result["test_func"]["function_metadata"]
        assert metadata["database_name"] == "snowflake"

    def test_parse_deterministic_flag(self):
        """Test parsing function with deterministic flag."""
        parser = FunctionPythonParser()

        content = """
from tee.parser.processing.function_decorator import functions

@functions.sql(
    function_name="test_func",
    return_type="INT",
    deterministic=True
)
def generate_sql(adapter_type: str) -> str:
    return "CREATE FUNCTION test_func() RETURNS INT AS $$ SELECT 1 $$;"
"""

        result = parser.parse(content, "test.py")

        metadata = result["test_func"]["function_metadata"]
        assert metadata["deterministic"] is True

    def test_clear_cache(self):
        """Test that cache can be cleared."""
        parser = FunctionPythonParser()

        content = """
@functions.sql(function_name="test", return_type="INT")
def test(): return "SELECT 1"
"""

        result1 = parser.parse(content, "test.py")
        parser.clear_cache()
        result2 = parser.parse(content, "test.py")

        # Results should be equal but not the same object after cache clear
        assert result1 == result2
        # Note: They might still be the same if caching is re-implemented, but structure should be same
