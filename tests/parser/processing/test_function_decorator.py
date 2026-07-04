"""
Unit tests for function decorators.
"""

import pytest

from t4t.parser.processing.function_decorator import FunctionDecoratorError, functions


class TestFunctionDecorators:
    """Test function decorators."""

    def test_sql_decorator_basic(self):
        """Test basic @functions.sql() decorator."""

        @functions.sql(function_name="test_func", return_type="FLOAT")
        def generate_sql(adapter_type: str) -> str:
            return "CREATE FUNCTION ..."

        assert hasattr(generate_sql, "_function_metadata")
        metadata = generate_sql._function_metadata
        assert metadata["function_name"] == "test_func"
        assert metadata["return_type"] == "FLOAT"
        assert metadata["function_type"] == "scalar"
        assert metadata["language"] == "sql"
        assert metadata["needs_evaluation"] is True

    def test_sql_decorator_with_all_params(self):
        """Test @functions.sql() with all parameters."""

        @functions.sql(
            function_name="complex_func",
            description="A complex function",
            function_type="table",
            parameters=[
                {"name": "x", "type": "FLOAT"},
                {"name": "y", "type": "INTEGER", "default": "0"},
            ],
            return_table_schema=[{"name": "result", "type": "FLOAT"}],
            schema="my_schema",
            deterministic=True,
            database_name="postgresql",
            tags=["analytics", "production"],
            object_tags={"category": "math", "sensitivity": "public"},
        )
        def generate_complex_sql(adapter_type: str) -> str:
            return "CREATE FUNCTION ..."

        metadata = generate_complex_sql._function_metadata
        assert metadata["function_name"] == "complex_func"
        assert metadata["description"] == "A complex function"
        assert metadata["function_type"] == "table"
        assert len(metadata["parameters"]) == 2
        assert metadata["schema"] == "my_schema"
        assert metadata["deterministic"] is True
        assert metadata["database_name"] == "postgresql"
        assert metadata["tags"] == ["analytics", "production"]
        assert metadata["object_tags"] == {"category": "math", "sensitivity": "public"}

    def test_sql_decorator_defaults(self):
        """Test @functions.sql() with defaults (uses function name)."""

        @functions.sql(return_type="INTEGER")
        def my_function(adapter_type: str) -> str:
            return "CREATE FUNCTION ..."

        metadata = my_function._function_metadata
        assert metadata["function_name"] == "my_function"
        assert metadata["function_type"] == "scalar"  # Default
        assert metadata["tags"] == []  # Default empty list
        assert metadata["object_tags"] == {}  # Default empty dict

    def test_python_decorator_basic(self):
        """Test basic @functions.python() decorator."""

        @functions.python(function_name="python_func", return_type="FLOAT")
        def python_func(x: float) -> float:
            return x * 2.0

        assert hasattr(python_func, "_function_metadata")
        metadata = python_func._function_metadata
        assert metadata["function_name"] == "python_func"
        assert metadata["return_type"] == "FLOAT"
        assert metadata["function_type"] == "scalar"
        assert metadata["language"] == "python"
        assert metadata["needs_evaluation"] is False

    def test_python_decorator_with_all_params(self):
        """Test @functions.python() with all parameters."""

        @functions.python(
            function_name="python_calc",
            description="Python calculator",
            function_type="scalar",
            parameters=[{"name": "x", "type": "FLOAT"}],
            return_type="FLOAT",
            schema="my_schema",
            deterministic=True,
            tags=["math"],
            object_tags={"category": "calculation"},
        )
        def python_calc(x: float) -> float:
            return x * 2.5

        metadata = python_calc._function_metadata
        assert metadata["function_name"] == "python_calc"
        assert metadata["description"] == "Python calculator"
        assert metadata["language"] == "python"
        assert metadata["tags"] == ["math"]

    def test_invalid_function_name(self):
        """Test decorator with invalid function name."""
        with pytest.raises(FunctionDecoratorError):

            @functions.sql(function_name="invalid-name!")
            def invalid_func(adapter_type: str) -> str:
                return "CREATE FUNCTION ..."

    def test_invalid_custom_function_name(self):
        """Test decorator with invalid custom function name."""
        with pytest.raises(FunctionDecoratorError):

            @functions.sql(function_name="invalid.name!")
            def valid_func(adapter_type: str) -> str:
                return "CREATE FUNCTION ..."

    def test_functions_namespace(self):
        """Test that functions namespace works correctly."""
        assert hasattr(functions, "sql")
        assert hasattr(functions, "python")
        assert callable(functions.sql)
        assert callable(functions.python)
