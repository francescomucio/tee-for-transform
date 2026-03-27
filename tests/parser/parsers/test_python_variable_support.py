"""
Test Python variable support functionality.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from tee.parser.parsers import PythonParser
from tee.parser.processing import model
from tee.parser.shared.registry import ModelRegistry


class TestPythonVariableSupport:
    """Test Python variable support in model functions."""

    @pytest.fixture(autouse=True)
    def clear_registry(self):
        """Clear model registry before and after each test."""
        ModelRegistry.clear()
        yield
        ModelRegistry.clear()

    def test_model_decorator_with_variables(self):
        """Test that the model decorator correctly stores variables."""

        @model(table_name="test_table", description="Test model", variables=["env", "debug"])
        def test_function():
            return "SELECT * FROM users"

        # Check that variables are stored in metadata
        assert hasattr(test_function, "_model_metadata")
        assert test_function._model_metadata["variables"] == ["env", "debug"]
        assert test_function._model_metadata["table_name"] == "test_table"
        assert test_function._model_metadata["description"] == "Test model"

    def test_model_decorator_without_variables(self):
        """Test that the model decorator works without variables."""

        @model(table_name="test_table")
        def test_function():
            return "SELECT * FROM users"

        # Check that variables defaults to empty list
        assert hasattr(test_function, "_model_metadata")
        assert test_function._model_metadata["variables"] == []

    def test_variable_injection_in_execution(self):
        """Test that variables are properly injected during function execution."""
        parser = PythonParser()

        # Create a test Python file with a model that uses variables
        test_file = Path("test_variable_injection.py")
        test_content = """
from tee.parser.processing import model

@model(variables=["env", "debug"])
def test_model():
    return f"SELECT * FROM users WHERE env = '{env}'"
"""

        try:
            # Write test file
            test_file.write_text(test_content)

            # Convert to absolute path for proper file_path matching
            test_file_abs = test_file.resolve()

            # Parse the file
            parsed_models = parser.parse(test_file.read_text(), file_path=test_file_abs)

            # Check that the model was parsed correctly
            assert len(parsed_models) == 1
            model_data = list(parsed_models.values())[0]
            assert model_data["model_metadata"]["variables"] == ["env", "debug"]

            # Test variable injection
            variables = {"env": "production", "debug": True}

            # Mock the module execution to avoid import issues
            with (
                patch.object(parser, "_execute_function") as mock_execute,
                patch.object(parser._sql_parser, "parse") as mock_parse,
            ):
                mock_execute.return_value = "SELECT * FROM users"
                mock_parse.return_value = {
                    "code": {
                        "sql": {
                            "original_sql": "SELECT * FROM users",
                            "resolved_sql": "SELECT * FROM users",
                            "source_tables": [],
                            "source_functions": [],
                        }
                    },
                    "sqlglot_hash": "test_hash",
                }

                # Execute the model with variables
                parser.evaluate_model_function(model_data, "test_schema.test_model", variables)

                # Verify that _execute_function was called with variables
                mock_execute.assert_called_once()
                call_args = mock_execute.call_args
                assert call_args[0][2] == variables  # Third argument should be variables

        finally:
            # Clean up test file
            if test_file.exists():
                test_file.unlink()

    def test_nested_variable_access(self):
        """Test that nested variables can be accessed in Python models."""
        parser = PythonParser()

        # Create a test Python file with nested variable access
        test_file = Path("test_nested_variables.py")
        test_content = """
from tee.parser.processing import model

@model(variables=["config"])
def test_nested_model():
    return f"SELECT * FROM users WHERE host = '{config.database.host}'"
"""

        try:
            # Write test file
            test_file.write_text(test_content)

            # Convert to absolute path for proper file_path matching
            test_file_abs = test_file.resolve()

            # Parse the file
            parsed_models = parser.parse(test_file.read_text(), file_path=test_file_abs)

            # Check that the model was parsed correctly
            assert len(parsed_models) == 1
            model_data = list(parsed_models.values())[0]
            assert model_data["model_metadata"]["variables"] == ["config"]

            # Test nested variable injection
            variables = {"config": {"database": {"host": "localhost", "port": 5432}}}

            # Mock the module execution
            with (
                patch.object(parser, "_execute_function") as mock_execute,
                patch.object(parser._sql_parser, "parse") as mock_parse,
            ):
                mock_execute.return_value = "SELECT * FROM users"
                mock_parse.return_value = {
                    "code": {
                        "sql": {
                            "original_sql": "SELECT * FROM users",
                            "resolved_sql": "SELECT * FROM users",
                            "source_tables": [],
                            "source_functions": [],
                        }
                    },
                    "sqlglot_hash": "test_hash",
                }

                # Execute the model with nested variables
                parser.evaluate_model_function(
                    model_data, "test_schema.test_nested_model", variables
                )

                # Verify that _execute_function was called with variables
                mock_execute.assert_called_once()
                call_args = mock_execute.call_args
                assert call_args[0][2] == variables

        finally:
            # Clean up test file
            if test_file.exists():
                test_file.unlink()

    def test_execute_all_models_with_variables(self):
        """Test that execute_all_models passes variables to individual model execution."""
        parser = PythonParser()

        # Create test models
        model1_data = {
            "function_name": "test_model1",
            "file_path": "test1.py",
            "model_metadata": {
                "table_name": "test_model1",
                "file_path": "test1.py",
                "function_name": "test_model1",
                "variables": ["env"],
            },
            "needs_evaluation": True,
        }

        model2_data = {
            "function_name": "test_model2",
            "file_path": "test2.py",
            "model_metadata": {
                "table_name": "test_model2",
                "file_path": "test2.py",
                "function_name": "test_model2",
                "variables": ["debug"],
            },
            "needs_evaluation": True,
        }

        parsed_models = {
            "test_schema.test_model1": model1_data,
            "test_schema.test_model2": model2_data,
        }

        variables = {"env": "production", "debug": True}

        # Mock execute_model_function
        with patch.object(parser, "evaluate_model_function") as mock_execute:
            mock_execute.side_effect = lambda model_data, table_name, vars: {
                **model_data,
                "needs_execution": False,
                "code": {
                    "sql": {
                        "resolved_sql": "SELECT * FROM test",
                        "original_sql": "SELECT * FROM test",
                        "source_tables": [],
                    }
                },
            }

            # Execute all models with variables
            parser.evaluate_all_models(parsed_models, variables)

            # Verify that both models were executed with variables
            assert mock_execute.call_count == 2

            # Check that variables were passed to each call
            for call in mock_execute.call_args_list:
                call_args = call[0]
                assert call_args[2] == variables  # Third argument should be variables

    def test_variable_injection_error_handling(self):
        """Test error handling when variable injection fails."""
        parser = PythonParser()

        # Create a test model
        model_data = {
            "function_name": "test_model",
            "file_path": "test.py",
            "model_metadata": {
                "table_name": "test_model",
                "file_path": "test.py",
                "function_name": "test_model",
                "variables": ["env"],
            },
            "needs_evaluation": True,
        }

        variables = {"env": "production"}

        # Mock _execute_function to raise an exception
        with patch.object(parser, "_execute_function") as mock_execute:
            mock_execute.side_effect = Exception("Variable injection failed")

            # Execute should raise PythonModelError
            with pytest.raises(Exception) as exc_info:
                parser.evaluate_model_function(model_data, "test_schema.test_model", variables)

            assert "Variable injection failed" in str(exc_info.value)

    def test_empty_variables_handling(self):
        """Test that empty or None variables are handled correctly."""
        parser = PythonParser()

        # Create a test model
        model_data = {
            "function_name": "test_model",
            "file_path": "test.py",
            "model_metadata": {
                "table_name": "test_model",
                "file_path": "test.py",
                "function_name": "test_model",
                "variables": [],
            },
            "needs_evaluation": True,
        }

        # Test with None variables
        with (
            patch.object(parser, "_execute_function") as mock_execute,
            patch.object(parser._sql_parser, "parse") as mock_parse,
        ):
            mock_execute.return_value = "SELECT * FROM users"
            mock_parse.return_value = {
                "code": {
                    "sql": {
                        "original_sql": "SELECT * FROM users",
                        "resolved_sql": "SELECT * FROM users",
                        "source_tables": [],
                        "source_functions": [],
                    }
                },
                "sqlglot_hash": "test_hash",
            }

            parser.evaluate_model_function(model_data, "test_schema.test_model", None)

            # Verify that _execute_function was called with None variables
            mock_execute.assert_called_once()
            call_args = mock_execute.call_args
            assert call_args[0][2] is None

        # Test with empty variables - create a new parser instance to avoid cache issues
        parser2 = PythonParser()
        model_data2 = {
            "function_name": "test_model2",
            "file_path": "test2.py",
            "model_metadata": {
                "table_name": "test_model2",
                "file_path": "test2.py",
                "function_name": "test_model2",
                "variables": [],
            },
            "needs_evaluation": True,
        }

        with (
            patch.object(parser2, "_execute_function") as mock_execute2,
            patch.object(parser2._sql_parser, "parse") as mock_parse2,
        ):
            mock_execute2.return_value = "SELECT * FROM users"
            mock_parse2.return_value = {
                "code": {
                    "sql": {
                        "original_sql": "SELECT * FROM users",
                        "resolved_sql": "SELECT * FROM users",
                        "source_tables": [],
                        "source_functions": [],
                    }
                },
                "sqlglot_hash": "test_hash",
            }

            parser2.evaluate_model_function(model_data2, "test_schema.test_model2", {})

            # Verify that _execute_function was called with empty variables
            mock_execute2.assert_called_once()
            call_args = mock_execute2.call_args
            assert call_args[0][2] == {}


if __name__ == "__main__":
    pytest.main([__file__])
