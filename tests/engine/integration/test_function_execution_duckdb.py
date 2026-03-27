"""
Integration tests for function execution with DuckDB.

These tests verify that functions are correctly created and executed in DuckDB.
"""

import pytest

from tee.engine.execution_engine import ExecutionEngine
from tee.parser.core.orchestrator import ParserOrchestrator


@pytest.mark.integration
class TestFunctionExecutionDuckDB:
    """Integration tests for function execution with DuckDB."""

    @pytest.fixture
    def temp_project(self, temp_project_dir):
        """Create a temporary project with function files."""
        project_path = temp_project_dir
        functions_dir = project_path / "functions" / "my_schema"
        functions_dir.mkdir(parents=True, exist_ok=True)

        # Create a simple SQL function (DuckDB uses MACRO syntax)
        function_sql = functions_dir / "calculate_percentage.sql"
        function_sql.write_text("""
CREATE OR REPLACE MACRO calculate_percentage(numerator, denominator) AS (
    CASE
        WHEN denominator = 0 OR denominator IS NULL THEN NULL
        ELSE (numerator / denominator) * 100.0
    END
);
""")

        # Create function metadata
        function_metadata = functions_dir / "calculate_percentage.py"
        function_metadata.write_text("""
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
    "tags": ["math", "utility"],
}
""")

        # Create a model that uses the function
        models_dir = project_path / "models" / "my_schema"
        models_dir.mkdir(parents=True, exist_ok=True)
        model_sql = models_dir / "test_results.sql"
        model_sql.write_text("""
SELECT
    10.0 as numerator,
    20.0 as denominator,
    my_schema.calculate_percentage(10.0, 20.0) as percentage
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

        return project_path

    def test_execute_function_in_duckdb(self, temp_project, duckdb_config):
        """Test executing a function in DuckDB."""
        # Create execution engine
        engine = ExecutionEngine(
            config=duckdb_config,
            project_folder=str(temp_project),
        )
        engine.connect()

        try:
            # Parse functions
            orchestrator = ParserOrchestrator(
                project_folder=str(temp_project),
                connection=duckdb_config,
            )
            parsed_functions = orchestrator.discover_and_parse_functions()

            assert len(parsed_functions) == 1
            assert "my_schema.calculate_percentage" in parsed_functions

            # Build dependency graph to get execution order
            graph = orchestrator.build_dependency_graph()
            execution_order = graph["execution_order"]

            # Execute functions
            results = engine.execute_functions(parsed_functions, execution_order)

            # Verify function was executed
            assert len(results["executed_functions"]) == 1
            assert "my_schema.calculate_percentage" in results["executed_functions"]
            assert len(results["failed_functions"]) == 0

            # Test that function can be called with schema prefix (schema is created by adapter)
            result = engine.adapter.execute_query(
                "SELECT my_schema.calculate_percentage(10.0, 20.0) as result"
            )
            assert result[0][0] == 50.0

            # Test edge case (division by zero)
            result = engine.adapter.execute_query(
                "SELECT my_schema.calculate_percentage(10.0, 0.0) as result"
            )
            assert result[0][0] is None

        finally:
            engine.disconnect()

    def test_execute_function_before_model(self, temp_project, duckdb_config):
        """Test that functions are executed before models that depend on them."""
        # Create execution engine
        engine = ExecutionEngine(
            config=duckdb_config,
            project_folder=str(temp_project),
        )
        engine.connect()

        try:
            # Parse functions and models
            orchestrator = ParserOrchestrator(
                project_folder=str(temp_project),
                connection=duckdb_config,
            )
            parsed_functions = orchestrator.discover_and_parse_functions()
            parsed_models = orchestrator.discover_and_parse_models()

            # Build dependency graph
            graph = orchestrator.build_dependency_graph()
            execution_order = graph["execution_order"]

            # Verify function comes before model in execution order
            func_pos = execution_order.index("my_schema.calculate_percentage")
            model_pos = execution_order.index("my_schema.test_results")
            assert func_pos < model_pos, "Function should execute before model"

            # Execute functions first
            function_results = engine.execute_functions(parsed_functions, execution_order)
            assert len(function_results["executed_functions"]) == 1

            # Execute models
            model_results = engine.execute_models(parsed_models, execution_order)
            assert len(model_results["executed_tables"]) == 1
            assert "my_schema.test_results" in model_results["executed_tables"]

            # Verify model was created and contains correct data
            result = engine.adapter.execute_query("SELECT percentage FROM my_schema.test_results")
            assert result[0][0] == 50.0

        finally:
            engine.disconnect()

    def test_function_with_dependencies(self, temp_project, duckdb_config):
        """Test function that depends on another function."""
        functions_dir = temp_project / "functions" / "my_schema"

        # Create a second function that uses the first one
        # Note: Must use schema prefix when calling the first function
        function2_sql = functions_dir / "calculate_double_percentage.sql"
        function2_sql.write_text("""
CREATE OR REPLACE MACRO calculate_double_percentage(numerator, denominator) AS (
    my_schema.calculate_percentage(numerator, denominator) * 2.0
);
""")

        function2_metadata = functions_dir / "calculate_double_percentage.py"
        function2_metadata.write_text("""
metadata = {
    "function_name": "calculate_double_percentage",
    "description": "Calculate double percentage",
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

        engine = ExecutionEngine(
            config=duckdb_config,
            project_folder=str(temp_project),
        )
        engine.connect()

        try:
            # Parse functions
            orchestrator = ParserOrchestrator(
                project_folder=str(temp_project),
                connection=duckdb_config,
            )
            parsed_functions = orchestrator.discover_and_parse_functions()

            assert len(parsed_functions) == 2

            # Build dependency graph
            graph = orchestrator.build_dependency_graph()
            execution_order = graph["execution_order"]

            # Verify execution order (calculate_percentage before calculate_double_percentage)
            func1_pos = execution_order.index("my_schema.calculate_percentage")
            func2_pos = execution_order.index("my_schema.calculate_double_percentage")
            assert func1_pos < func2_pos

            # Execute functions
            results = engine.execute_functions(parsed_functions, execution_order)

            # Verify both functions were executed
            assert len(results["executed_functions"]) == 2
            assert "my_schema.calculate_percentage" in results["executed_functions"]
            assert "my_schema.calculate_double_percentage" in results["executed_functions"]

            # Test the dependent function
            result = engine.adapter.execute_query(
                "SELECT my_schema.calculate_double_percentage(10.0, 20.0) as result"
            )
            assert result[0][0] == 100.0

        finally:
            engine.disconnect()

    def test_function_execution_error_handling(self, temp_project, duckdb_config):
        """Test that function execution errors are handled gracefully."""
        functions_dir = temp_project / "functions" / "my_schema"

        # Create a function with invalid SQL
        invalid_function = functions_dir / "invalid_function.sql"
        invalid_function.write_text("""
CREATE OR REPLACE MACRO invalid_function(x) AS (
    invalid_column_name  -- This will cause an error
);
""")

        invalid_metadata = functions_dir / "invalid_function.py"
        invalid_metadata.write_text("""
metadata = {
    "function_name": "invalid_function",
    "function_type": "scalar",
    "language": "sql",
    "parameters": [{"name": "x", "type": "DOUBLE"}],
    "return_type": "DOUBLE",
}
""")

        engine = ExecutionEngine(
            config=duckdb_config,
            project_folder=str(temp_project),
        )
        engine.connect()

        try:
            # Parse functions
            orchestrator = ParserOrchestrator(
                project_folder=str(temp_project),
                connection=duckdb_config,
            )
            parsed_functions = orchestrator.discover_and_parse_functions()

            # Build dependency graph
            graph = orchestrator.build_dependency_graph()
            execution_order = graph["execution_order"]

            # Execute functions (should handle errors gracefully)
            results = engine.execute_functions(parsed_functions, execution_order)

            # Verify that valid function was executed
            assert "my_schema.calculate_percentage" in results["executed_functions"]

            # Verify that invalid function failed
            failed_functions = {f["function"] for f in results["failed_functions"]}
            assert "my_schema.invalid_function" in failed_functions

            # Verify that valid function still works (test by calling it)
            result = engine.adapter.execute_query(
                "SELECT my_schema.calculate_percentage(10.0, 20.0) as result"
            )
            assert result[0][0] == 50.0

        finally:
            engine.disconnect()

    def test_function_tags_attachment(self, temp_project, duckdb_config):
        """Test that function tags are attached (DuckDB logs debug for tags)."""
        engine = ExecutionEngine(
            config=duckdb_config,
            project_folder=str(temp_project),
        )
        engine.connect()

        try:
            # Parse functions
            orchestrator = ParserOrchestrator(
                project_folder=str(temp_project),
                connection=duckdb_config,
            )
            parsed_functions = orchestrator.discover_and_parse_functions()

            # Build dependency graph
            graph = orchestrator.build_dependency_graph()
            execution_order = graph["execution_order"]

            # Execute functions
            results = engine.execute_functions(parsed_functions, execution_order)

            # Verify function was executed (tags are logged but not attached in DuckDB)
            assert len(results["executed_functions"]) == 1

        finally:
            engine.disconnect()


@pytest.mark.integration
class TestFunctionExecutionFullWorkflow:
    """Integration tests for full workflow with functions (DuckDB)."""

    @pytest.fixture
    def temp_project_full(self, temp_project_dir):
        """Create a complete project with seeds, functions, and models."""
        project_path = temp_project_dir

        # Create seeds (in schema subfolder to create my_schema.source_data)
        seeds_dir = project_path / "seeds" / "my_schema"
        seeds_dir.mkdir(parents=True, exist_ok=True)
        seed_file = seeds_dir / "source_data.csv"
        seed_file.write_text("id,name,value\n1,Alice,10.0\n2,Bob,20.0\n3,Charlie,30.0\n")

        # Create functions (DuckDB uses MACRO syntax)
        functions_dir = project_path / "functions" / "my_schema"
        functions_dir.mkdir(parents=True, exist_ok=True)
        function_sql = functions_dir / "calculate_percentage.sql"
        function_sql.write_text("""
CREATE OR REPLACE MACRO calculate_percentage(numerator, denominator) AS (
    CASE
        WHEN denominator = 0 OR denominator IS NULL THEN NULL
        ELSE (numerator / denominator) * 100.0
    END
);
""")

        # Create models
        models_dir = project_path / "models" / "my_schema"
        models_dir.mkdir(parents=True, exist_ok=True)
        model_sql = models_dir / "results.sql"
        model_sql.write_text("""
SELECT
    id,
    name,
    value,
    my_schema.calculate_percentage(value, 100.0) as percentage
FROM my_schema.source_data
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

        return project_path

    def test_full_workflow_seeds_functions_models(self, temp_project_full, duckdb_config):
        """Test complete workflow: Seeds → Functions → Models."""
        from tee.executor import build_models

        # Create project config
        project_config = {
            "name": "test_project",
            "connection": duckdb_config,
        }

        # Execute full build workflow
        results = build_models(
            project_folder=str(temp_project_full),
            connection_config=duckdb_config,
            save_analysis=False,
            project_config=project_config,
        )

        # Verify execution order
        assert "executed_functions" in results or len(results.get("executed_tables", [])) > 0

        # Verify model was created
        engine = ExecutionEngine(config=duckdb_config, project_folder=str(temp_project_full))
        engine.connect()

        try:
            # Verify function exists (test by calling it)
            result = engine.adapter.execute_query(
                "SELECT my_schema.calculate_percentage(10.0, 20.0) as result"
            )
            assert result[0][0] == 50.0

            # Verify model was created and contains correct data
            result = engine.adapter.execute_query("SELECT COUNT(*) FROM my_schema.results")
            assert result[0][0] == 3

            # Verify function was used correctly
            result = engine.adapter.execute_query(
                "SELECT percentage FROM my_schema.results WHERE id = 1"
            )
            assert result[0][0] == 10.0  # 10.0 / 100.0 * 100 = 10.0

        finally:
            engine.disconnect()
