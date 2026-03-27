"""
Complex dependency scenario tests for functions.
"""

from tee.parser.core.orchestrator import ParserOrchestrator


class TestComplexFunctionDependencies:
    """Test complex function dependency scenarios."""

    def test_function_chain_with_models(self, tmp_path):
        """Test: table → func1 → func2 → model."""
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
CREATE FUNCTION base_calc(x DOUBLE) RETURNS DOUBLE AS $$
    SELECT x * 2 FROM source WHERE id = 1
$$;
""")

        # Create func2 that depends on func1
        func2_sql = schema_folder / "advanced_calc.sql"
        func2_sql.write_text("""
CREATE FUNCTION advanced_calc(x DOUBLE) RETURNS DOUBLE AS $$
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

        orchestrator = ParserOrchestrator(
            project_folder=str(tmp_path),
            connection={"type": "duckdb"},
        )

        orchestrator.discover_and_parse_functions()
        orchestrator.discover_and_parse_models()

        graph = orchestrator.build_dependency_graph()

        # Verify dependency chain
        assert "my_schema.base_calc" in graph["nodes"]
        assert "my_schema.advanced_calc" in graph["nodes"]
        assert "my_schema.result" in graph["nodes"]

        # Verify dependencies
        advanced_deps = graph["dependencies"].get("my_schema.advanced_calc", [])
        assert "my_schema.base_calc" in advanced_deps

        result_deps = graph["dependencies"].get("my_schema.result", [])
        assert "my_schema.advanced_calc" in result_deps

    def test_function_depends_on_multiple_functions(self, tmp_path):
        """Test function calling multiple other functions."""
        models_folder = tmp_path / "models"
        models_folder.mkdir()
        functions_folder = tmp_path / "functions"
        functions_folder.mkdir()
        schema_folder = functions_folder / "my_schema"
        schema_folder.mkdir()

        # Create func1
        func1_sql = schema_folder / "add.sql"
        func1_sql.write_text("CREATE FUNCTION add(x INT, y INT) RETURNS INT AS $$ SELECT x + y $$;")

        # Create func2
        func2_sql = schema_folder / "multiply.sql"
        func2_sql.write_text(
            "CREATE FUNCTION multiply(x INT, y INT) RETURNS INT AS $$ SELECT x * y $$;"
        )

        # Create func3 that depends on both func1 and func2
        func3_sql = schema_folder / "complex_calc.sql"
        func3_sql.write_text("""
CREATE FUNCTION complex_calc(x INT, y INT) RETURNS INT AS $$
    SELECT add(x, y) + multiply(x, y)
$$;
""")

        orchestrator = ParserOrchestrator(
            project_folder=str(tmp_path),
            connection={"type": "duckdb"},
        )

        orchestrator.discover_and_parse_functions()
        graph = orchestrator.build_dependency_graph()

        # Verify func3 depends on both func1 and func2
        complex_deps = graph["dependencies"].get("my_schema.complex_calc", [])
        assert "my_schema.add" in complex_deps
        assert "my_schema.multiply" in complex_deps

    def test_model_uses_multiple_functions(self, tmp_path):
        """Test model calling multiple functions."""
        models_folder = tmp_path / "models"
        models_folder.mkdir()
        functions_folder = tmp_path / "functions"
        functions_folder.mkdir()
        schema_folder = functions_folder / "my_schema"
        schema_folder.mkdir()

        # Create func1
        func1_sql = schema_folder / "format_name.sql"
        func1_sql.write_text(
            "CREATE FUNCTION format_name(n VARCHAR) RETURNS VARCHAR AS $$ SELECT UPPER(n) $$;"
        )

        # Create func2
        func2_sql = schema_folder / "calculate_age.sql"
        func2_sql.write_text(
            "CREATE FUNCTION calculate_age(birth_date DATE) RETURNS INT AS $$ SELECT 25 $$;"
        )

        # Create model that uses both functions
        model_sql = models_folder / "my_schema" / "result.sql"
        model_sql.parent.mkdir(parents=True, exist_ok=True)
        model_sql.write_text("""
SELECT
    format_name('john') as name,
    calculate_age('1990-01-01'::DATE) as age
""")

        orchestrator = ParserOrchestrator(
            project_folder=str(tmp_path),
            connection={"type": "duckdb"},
        )

        orchestrator.discover_and_parse_functions()
        orchestrator.discover_and_parse_models()

        graph = orchestrator.build_dependency_graph()

        # Verify model depends on both functions
        result_deps = graph["dependencies"].get("my_schema.result", [])
        assert "my_schema.format_name" in result_deps
        assert "my_schema.calculate_age" in result_deps

    def test_function_and_model_mixed_dependencies(self, tmp_path):
        """Test complex mixed dependencies."""
        models_folder = tmp_path / "models"
        models_folder.mkdir()
        functions_folder = tmp_path / "functions"
        functions_folder.mkdir()
        schema_folder = functions_folder / "my_schema"
        schema_folder.mkdir()

        # Create source table
        source_sql = models_folder / "my_schema" / "source.sql"
        source_sql.parent.mkdir(parents=True, exist_ok=True)
        source_sql.write_text("SELECT 1 as id")

        # Create intermediate model
        intermediate_sql = models_folder / "my_schema" / "intermediate.sql"
        intermediate_sql.write_text("SELECT id FROM source")

        # Create func1 that depends on source table
        func1_sql = schema_folder / "helper.sql"
        func1_sql.write_text("""
CREATE FUNCTION helper(x INT) RETURNS INT AS $$
    SELECT x * 2 FROM source WHERE id = x
$$;
""")

        # Create func2 that depends on func1
        func2_sql = schema_folder / "processor.sql"
        func2_sql.write_text("""
CREATE FUNCTION processor(x INT) RETURNS INT AS $$
    SELECT helper(x) + 1
$$;
""")

        # Create final model that depends on intermediate, func2, and source
        final_sql = models_folder / "my_schema" / "final.sql"
        final_sql.write_text("""
SELECT
    i.id,
    processor(i.id) as processed,
    s.id as source_id
FROM intermediate i
JOIN source s ON i.id = s.id
""")

        orchestrator = ParserOrchestrator(
            project_folder=str(tmp_path),
            connection={"type": "duckdb"},
        )

        orchestrator.discover_and_parse_functions()
        orchestrator.discover_and_parse_models()

        graph = orchestrator.build_dependency_graph()

        # Verify all dependencies
        assert "my_schema.source" in graph["nodes"]
        assert "my_schema.intermediate" in graph["nodes"]
        assert "my_schema.helper" in graph["nodes"]
        assert "my_schema.processor" in graph["nodes"]
        assert "my_schema.final" in graph["nodes"]

        # Verify dependency chain
        intermediate_deps = graph["dependencies"].get("my_schema.intermediate", [])
        assert "my_schema.source" in intermediate_deps

        processor_deps = graph["dependencies"].get("my_schema.processor", [])
        assert "my_schema.helper" in processor_deps

        final_deps = graph["dependencies"].get("my_schema.final", [])
        assert "my_schema.intermediate" in final_deps
        assert "my_schema.processor" in final_deps
        assert "my_schema.source" in final_deps

        # Verify execution order
        execution_order = graph["execution_order"]
        source_pos = execution_order.index("my_schema.source")
        intermediate_pos = execution_order.index("my_schema.intermediate")
        helper_pos = execution_order.index("my_schema.helper")
        processor_pos = execution_order.index("my_schema.processor")
        final_pos = execution_order.index("my_schema.final")

        # Verify correct order
        assert source_pos < intermediate_pos
        assert source_pos < helper_pos
        assert helper_pos < processor_pos
        assert intermediate_pos < final_pos
        assert processor_pos < final_pos
