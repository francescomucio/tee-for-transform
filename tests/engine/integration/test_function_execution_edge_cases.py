"""
Additional integration tests for function execution edge cases.

These tests cover:
- Function overloading scenarios
- Error recovery
- Complex dependency chains
- Signature checking
"""

import pytest

from t4t.engine.execution_engine import ExecutionEngine
from t4t.parser.core.orchestrator import ParserOrchestrator


@pytest.mark.integration
class TestFunctionExecutionEdgeCases:
    """Edge case tests for function execution."""

    @pytest.fixture
    def temp_project_overload(self, temp_project_dir):
        """Create a temporary project with overloaded functions."""
        project_path = temp_project_dir
        functions_dir = project_path / "functions" / "my_schema"
        functions_dir.mkdir(parents=True, exist_ok=True)

        # Create first overload: calculate_percentage(FLOAT, FLOAT)
        function_sql1 = functions_dir / "calculate_percentage.sql"
        function_sql1.write_text("""
CREATE OR REPLACE MACRO calculate_percentage(numerator, denominator) AS (
    CASE
        WHEN denominator = 0 OR denominator IS NULL THEN NULL
        ELSE (numerator / denominator) * 100.0
    END
);
""")

        function_metadata1 = functions_dir / "calculate_percentage.py"
        function_metadata1.write_text("""
metadata = {
    "function_name": "calculate_percentage",
    "description": "Calculate percentage from numerator and denominator",
    "function_type": "scalar",
    "language": "sql",
    "parameters": [
        {"name": "numerator", "type": "DOUBLE"},
        {"name": "denominator", "type": "DOUBLE"}
    ],
    "return_type": "DOUBLE",
    "deterministic": True,
}
""")

        # Create models folder
        models_dir = project_path / "models"
        models_dir.mkdir(parents=True, exist_ok=True)

        # Create project.toml
        project_toml = project_path / "project.toml"
        project_toml.write_text("""
name = "test_project"
[connection]
type = "duckdb"
path = ":memory:"
schema = "my_schema"
""")

        return project_path

    def test_function_creation_without_existence_check(self, temp_project_overload, duckdb_config):
        """Test that functions are created directly without checking existence first."""
        engine = ExecutionEngine(
            config=duckdb_config,
            project_folder=str(temp_project_overload),
        )
        engine.connect()

        try:
            # Parse functions
            orchestrator = ParserOrchestrator(
                project_folder=str(temp_project_overload),
                connection=duckdb_config,
            )
            parsed_functions = orchestrator.discover_and_parse_functions()

            assert len(parsed_functions) == 1
            function_name = "my_schema.calculate_percentage"
            assert function_name in parsed_functions

            graph = orchestrator.build_dependency_graph()
            execution_order = graph["execution_order"]

            # Execute functions - should work without checking existence first
            # CREATE OR REPLACE handles replacement automatically
            results = engine.execute_functions(parsed_functions, execution_order)
            assert len(results["executed_functions"]) == 1
            assert function_name in results["executed_functions"]

            # Verify function works
            result = engine.adapter.execute_query(f"SELECT {function_name}(10.0, 20.0) as result")
            assert result[0][0] == 50.0

        finally:
            engine.disconnect()

    def test_function_replace_without_existence_check(self, temp_project_overload, duckdb_config):
        """Test that CREATE OR REPLACE works without checking existence first."""
        engine = ExecutionEngine(
            config=duckdb_config,
            project_folder=str(temp_project_overload),
        )
        engine.connect()

        try:
            # Parse and execute functions
            orchestrator = ParserOrchestrator(
                project_folder=str(temp_project_overload),
                connection=duckdb_config,
            )
            parsed_functions = orchestrator.discover_and_parse_functions()

            graph = orchestrator.build_dependency_graph()
            execution_order = graph["execution_order"]

            # Execute functions first time
            results = engine.execute_functions(parsed_functions, execution_order)
            assert len(results["executed_functions"]) == 1

            function_name = "my_schema.calculate_percentage"

            # Verify function works
            result = engine.adapter.execute_query(f"SELECT {function_name}(10.0, 20.0) as result")
            assert result[0][0] == 50.0

            # Execute again - CREATE OR REPLACE should handle replacement
            # No need to check existence, just replace
            results2 = engine.execute_functions(parsed_functions, execution_order)
            assert len(results2["executed_functions"]) == 1
            assert function_name in results2["executed_functions"]

            # Function should still work after replacement
            result2 = engine.adapter.execute_query(f"SELECT {function_name}(10.0, 20.0) as result")
            assert result2[0][0] == 50.0

        finally:
            engine.disconnect()

    def test_function_execution_continues_on_error(self, temp_project_dir, duckdb_config):
        """Test that function execution continues even if one function fails."""
        project_path = temp_project_dir
        functions_dir = project_path / "functions" / "my_schema"
        functions_dir.mkdir(parents=True, exist_ok=True)
        models_dir = project_path / "models"
        models_dir.mkdir(parents=True, exist_ok=True)

        # Create a valid function
        valid_function = functions_dir / "valid_function.sql"
        valid_function.write_text("""
CREATE OR REPLACE MACRO valid_function(x) AS (x * 2);
""")

        valid_metadata = functions_dir / "valid_function.py"
        valid_metadata.write_text("""
metadata = {
    "function_name": "valid_function",
    "parameters": [{"name": "x", "type": "DOUBLE"}],
}
""")

        # Create an invalid function (syntax error)
        invalid_function = functions_dir / "invalid_function.sql"
        invalid_function.write_text("""
CREATE OR REPLACE MACRO invalid_function(x) AS (INVALID SYNTAX HERE);
""")

        invalid_metadata = functions_dir / "invalid_function.py"
        invalid_metadata.write_text("""
metadata = {
    "function_name": "invalid_function",
    "parameters": [{"name": "x", "type": "DOUBLE"}],
}
""")

        # Create project.toml
        project_toml = project_path / "project.toml"
        project_toml.write_text("""
name = "test_project"
[connection]
type = "duckdb"
path = ":memory:"
schema = "my_schema"
""")

        engine = ExecutionEngine(
            config=duckdb_config,
            project_folder=str(project_path),
        )
        engine.connect()

        try:
            orchestrator = ParserOrchestrator(
                project_folder=str(project_path),
                connection=duckdb_config,
            )
            parsed_functions = orchestrator.discover_and_parse_functions()
            graph = orchestrator.build_dependency_graph()
            execution_order = graph["execution_order"]

            # Execute functions - should continue even if one fails
            results = engine.execute_functions(parsed_functions, execution_order)

            # Valid function should succeed
            assert "my_schema.valid_function" in results["executed_functions"]

            # Invalid function should fail
            assert len(results["failed_functions"]) == 1
            assert any(
                f["function"] == "my_schema.invalid_function" for f in results["failed_functions"]
            )

        finally:
            engine.disconnect()

    def test_complex_function_dependency_chain(self, temp_project_dir, duckdb_config):
        """Test execution order with complex function dependency chain."""
        project_path = temp_project_dir
        functions_dir = project_path / "functions" / "my_schema"
        functions_dir.mkdir(parents=True, exist_ok=True)
        models_dir = project_path / "models"
        models_dir.mkdir(parents=True, exist_ok=True)

        # Function 1: base function (no dependencies)
        func1 = functions_dir / "base_func.sql"
        func1.write_text("CREATE OR REPLACE MACRO base_func(x) AS (x + 1);")
        func1_meta = functions_dir / "base_func.py"
        func1_meta.write_text("""
metadata = {"function_name": "base_func", "parameters": [{"name": "x", "type": "DOUBLE"}]}
""")

        # Function 2: depends on base_func
        func2 = functions_dir / "middle_func.sql"
        func2.write_text("CREATE OR REPLACE MACRO middle_func(x) AS (my_schema.base_func(x) * 2);")
        func2_meta = functions_dir / "middle_func.py"
        func2_meta.write_text("""
metadata = {"function_name": "middle_func", "parameters": [{"name": "x", "type": "DOUBLE"}]}
""")

        # Function 3: depends on middle_func
        func3 = functions_dir / "top_func.sql"
        func3.write_text("CREATE OR REPLACE MACRO top_func(x) AS (my_schema.middle_func(x) + 10);")
        func3_meta = functions_dir / "top_func.py"
        func3_meta.write_text("""
metadata = {"function_name": "top_func", "parameters": [{"name": "x", "type": "DOUBLE"}]}
""")

        # Model depends on top_func
        model = models_dir / "result.sql"
        model.write_text("SELECT my_schema.top_func(5.0) as result")

        project_toml = project_path / "project.toml"
        project_toml.write_text("""
name = "test_project"
[connection]
type = "duckdb"
path = ":memory:"
schema = "my_schema"
""")

        engine = ExecutionEngine(
            config=duckdb_config,
            project_folder=str(project_path),
        )
        engine.connect()

        try:
            orchestrator = ParserOrchestrator(
                project_folder=str(project_path),
                connection=duckdb_config,
            )
            parsed_functions = orchestrator.discover_and_parse_functions()
            graph = orchestrator.build_dependency_graph()
            execution_order = graph["execution_order"]

            # Execute functions
            results = engine.execute_functions(parsed_functions, execution_order)

            # All functions should execute successfully
            assert len(results["executed_functions"]) == 3
            assert "my_schema.base_func" in results["executed_functions"]
            assert "my_schema.middle_func" in results["executed_functions"]
            assert "my_schema.top_func" in results["executed_functions"]
            assert len(results["failed_functions"]) == 0

            # Verify execution order: base_func should come before middle_func, which should come before top_func
            executed = results["executed_functions"]
            base_pos = executed.index("my_schema.base_func")
            middle_pos = executed.index("my_schema.middle_func")
            top_pos = executed.index("my_schema.top_func")

            assert base_pos < middle_pos < top_pos

            # Verify the chain works by calling top_func
            result = engine.adapter.execute_query("SELECT my_schema.top_func(5.0) as result")
            assert len(result) > 0
            # base_func(5) = 6, middle_func(6) = 12, top_func(12) = 22
            assert result[0][0] == 22.0

        finally:
            engine.disconnect()
