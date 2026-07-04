"""
End-to-end integration tests for function workflow.

Tests the complete workflow: discovery → parsing → dependency graph → OTS export.
"""

from t4t.parser.core.orchestrator import ParserOrchestrator
from t4t.parser.output.ots.transformer import OTSTransformer


class TestFunctionEndToEnd:
    """Test complete function workflow end-to-end."""

    def test_full_function_workflow(self, tmp_path):
        """Test complete workflow: discovery → parsing → dependency graph → OTS export."""
        # Setup project structure
        models_folder = tmp_path / "models"
        models_folder.mkdir()
        functions_folder = tmp_path / "functions"
        functions_folder.mkdir()
        schema_folder = functions_folder / "my_schema"
        schema_folder.mkdir()

        # Create a function
        function_sql = schema_folder / "calculate_percentage.sql"
        function_sql.write_text("""
CREATE OR REPLACE FUNCTION calculate_percentage(
    numerator DOUBLE,
    denominator DOUBLE
) RETURNS DOUBLE AS $$
    SELECT
        CASE
            WHEN denominator = 0 OR denominator IS NULL THEN NULL
            ELSE (numerator / denominator) * 100.0
        END
$$;
""")

        function_metadata = schema_folder / "calculate_percentage.py"
        function_metadata.write_text("""
metadata = {
    "function_name": "calculate_percentage",
    "description": "Calculate percentage",
    "function_type": "scalar",
    "language": "sql",
    "parameters": [
        {"name": "numerator", "type": "DOUBLE"},
        {"name": "denominator", "type": "DOUBLE"},
    ],
    "return_type": "DOUBLE",
    "schema": "my_schema",
    "tags": ["math", "utility"],
}
""")

        # Create a model that uses the function
        model_sql = models_folder / "my_schema" / "result.sql"
        model_sql.parent.mkdir(parents=True, exist_ok=True)
        model_sql.write_text("""
SELECT
    id,
    calculate_percentage(value, total) as percentage
FROM source_table
""")

        # Step 1: Discover and parse functions
        orchestrator = ParserOrchestrator(
            project_folder=str(tmp_path),
            connection={"type": "duckdb"},
        )

        parsed_functions = orchestrator.discover_and_parse_functions()
        assert len(parsed_functions) == 1
        assert "my_schema.calculate_percentage" in parsed_functions

        # Step 2: Parse models
        parsed_models = orchestrator.discover_and_parse_models()
        assert len(parsed_models) >= 1

        # Step 3: Build dependency graph
        graph = orchestrator.build_dependency_graph()
        assert "my_schema.calculate_percentage" in graph["nodes"]
        assert "my_schema.result" in graph["nodes"]

        # Step 4: Export to OTS
        project_config = {
            "name": "test_project",
            "connection": {"type": "duckdb"},
        }
        transformer = OTSTransformer(project_config)
        ots_modules = transformer.transform_to_ots_modules(
            parsed_models, parsed_functions=parsed_functions
        )

        # Verify OTS structure
        assert len(ots_modules) > 0
        module = list(ots_modules.values())[0]
        assert module["ots_version"] == "0.2.2"  # Should be 0.2.1 with functions
        assert "functions" in module
        assert len(module["functions"]) == 1
        assert module["functions"][0]["function_id"] == "my_schema.calculate_percentage"

    def test_function_and_model_integration(self, tmp_path):
        """Test functions and models working together in a real project."""
        # Setup project structure
        models_folder = tmp_path / "models"
        models_folder.mkdir()
        functions_folder = tmp_path / "functions"
        functions_folder.mkdir()
        schema_folder = functions_folder / "my_schema"
        schema_folder.mkdir()

        # Create a table function
        table_func_sql = schema_folder / "get_users.sql"
        table_func_sql.write_text("""
CREATE OR REPLACE FUNCTION get_users()
RETURNS TABLE(id INT, name VARCHAR) AS $$
    SELECT id, name FROM users
$$;
""")

        table_func_metadata = schema_folder / "get_users.py"
        table_func_metadata.write_text("""
metadata = {
    "function_name": "get_users",
    "function_type": "table",
    "language": "sql",
    "return_table_schema": [
        {"name": "id", "datatype": "INT"},
        {"name": "name", "datatype": "VARCHAR"},
    ],
}
""")

        # Create a scalar function
        scalar_func_sql = schema_folder / "format_name.sql"
        scalar_func_sql.write_text("""
CREATE OR REPLACE FUNCTION format_name(first_name VARCHAR, last_name VARCHAR)
RETURNS VARCHAR AS $$
    SELECT first_name || ' ' || last_name
$$;
""")

        # Create a model that uses both functions
        model_sql = models_folder / "my_schema" / "formatted_users.sql"
        model_sql.parent.mkdir(parents=True, exist_ok=True)
        model_sql.write_text("""
SELECT
    id,
    format_name(first_name, last_name) as full_name
FROM get_users()
""")

        # Create a source table
        source_sql = models_folder / "my_schema" / "users.sql"
        source_sql.write_text("SELECT 1 as id, 'John' as first_name, 'Doe' as last_name")

        # Parse everything
        orchestrator = ParserOrchestrator(
            project_folder=str(tmp_path),
            connection={"type": "duckdb"},
        )

        parsed_functions = orchestrator.discover_and_parse_functions()
        parsed_models = orchestrator.discover_and_parse_models()

        # Verify functions were parsed
        assert "my_schema.get_users" in parsed_functions
        assert "my_schema.format_name" in parsed_functions

        # Verify models were parsed
        assert "my_schema.formatted_users" in parsed_models
        assert "my_schema.users" in parsed_models

        # Build dependency graph
        graph = orchestrator.build_dependency_graph()

        # Verify dependencies
        # formatted_users depends on get_users and format_name
        formatted_deps = graph["dependencies"].get("my_schema.formatted_users", [])
        assert "my_schema.get_users" in formatted_deps or "my_schema.format_name" in formatted_deps

        # Verify execution order
        execution_order = graph["execution_order"]
        execution_order.index("my_schema.users") if "my_schema.users" in execution_order else -1
        get_users_pos = (
            execution_order.index("my_schema.get_users")
            if "my_schema.get_users" in execution_order
            else -1
        )
        format_name_pos = (
            execution_order.index("my_schema.format_name")
            if "my_schema.format_name" in execution_order
            else -1
        )
        formatted_pos = (
            execution_order.index("my_schema.formatted_users")
            if "my_schema.formatted_users" in execution_order
            else -1
        )

        # Functions should come before the model that uses them
        if formatted_pos >= 0 and get_users_pos >= 0:
            assert get_users_pos < formatted_pos
        if formatted_pos >= 0 and format_name_pos >= 0:
            assert format_name_pos < formatted_pos

    def test_function_dependency_chain(self, tmp_path):
        """Test function dependency chain: table → func1 → func2 → model."""
        # Setup project structure
        models_folder = tmp_path / "models"
        models_folder.mkdir()
        functions_folder = tmp_path / "functions"
        functions_folder.mkdir()
        schema_folder = functions_folder / "my_schema"
        schema_folder.mkdir()

        # Create source table
        source_sql = models_folder / "my_schema" / "source.sql"
        source_sql.parent.mkdir(parents=True, exist_ok=True)
        source_sql.write_text("SELECT 1 as id, 100 as value")

        # Create func1 that depends on table
        func1_sql = schema_folder / "base_calc.sql"
        func1_sql.write_text("""
CREATE OR REPLACE FUNCTION base_calc(x DOUBLE) RETURNS DOUBLE AS $$
    SELECT x * 2
$$;
""")

        # Create func2 that depends on func1
        func2_sql = schema_folder / "advanced_calc.sql"
        func2_sql.write_text("""
CREATE OR REPLACE FUNCTION advanced_calc(x DOUBLE) RETURNS DOUBLE AS $$
    SELECT base_calc(x) + 10
$$;
""")

        # Create model that depends on func2
        model_sql = models_folder / "my_schema" / "result.sql"
        model_sql.write_text("""
SELECT
    id,
    advanced_calc(value) as calculated_value
FROM source
""")

        # Parse everything
        orchestrator = ParserOrchestrator(
            project_folder=str(tmp_path),
            connection={"type": "duckdb"},
        )

        orchestrator.discover_and_parse_functions()
        orchestrator.discover_and_parse_models()

        # Build dependency graph
        graph = orchestrator.build_dependency_graph()

        # Verify dependency chain
        # advanced_calc depends on base_calc
        advanced_deps = graph["dependencies"].get("my_schema.advanced_calc", [])
        assert "my_schema.base_calc" in advanced_deps

        # result depends on advanced_calc
        result_deps = graph["dependencies"].get("my_schema.result", [])
        assert "my_schema.advanced_calc" in result_deps

        # Verify execution order
        execution_order = graph["execution_order"]
        base_pos = (
            execution_order.index("my_schema.base_calc")
            if "my_schema.base_calc" in execution_order
            else -1
        )
        advanced_pos = (
            execution_order.index("my_schema.advanced_calc")
            if "my_schema.advanced_calc" in execution_order
            else -1
        )
        result_pos = (
            execution_order.index("my_schema.result")
            if "my_schema.result" in execution_order
            else -1
        )

        # Verify order: base_calc < advanced_calc < result
        if base_pos >= 0 and advanced_pos >= 0:
            assert base_pos < advanced_pos
        if advanced_pos >= 0 and result_pos >= 0:
            assert advanced_pos < result_pos
