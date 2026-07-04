"""
Unit tests for function orchestration and integration.
"""

from t4t.parser.core.orchestrator import ParserOrchestrator


class TestFunctionOrchestration:
    """Test function orchestration in ParserOrchestrator."""

    def test_orchestrator_initializes_with_functions_folder(self, tmp_path):
        """Test that orchestrator initializes with functions folder."""
        models_folder = tmp_path / "models"
        models_folder.mkdir()
        functions_folder = tmp_path / "functions"
        functions_folder.mkdir()

        orchestrator = ParserOrchestrator(
            project_folder=str(tmp_path),
            connection={"type": "duckdb"},
        )

        assert orchestrator.functions_folder == functions_folder
        assert orchestrator.file_discovery.functions_folder == functions_folder

    def test_discover_and_parse_functions_empty_folder(self, tmp_path):
        """Test discovering functions in empty folder."""
        models_folder = tmp_path / "models"
        models_folder.mkdir()
        functions_folder = tmp_path / "functions"
        functions_folder.mkdir()

        orchestrator = ParserOrchestrator(
            project_folder=str(tmp_path),
            connection={"type": "duckdb"},
        )

        functions = orchestrator.discover_and_parse_functions()
        assert len(functions) == 0

    def test_discover_and_parse_sql_function(self, tmp_path):
        """Test discovering and parsing a SQL function."""
        models_folder = tmp_path / "models"
        models_folder.mkdir()
        functions_folder = tmp_path / "functions"
        functions_folder.mkdir()
        schema_folder = functions_folder / "my_schema"
        schema_folder.mkdir()

        # Create SQL function file
        sql_file = schema_folder / "test_func.sql"
        sql_file.write_text("""
        CREATE OR REPLACE FUNCTION test_func(
            x DOUBLE
        ) RETURNS DOUBLE AS $$
            SELECT x * 2.0
        $$;
        """)

        orchestrator = ParserOrchestrator(
            project_folder=str(tmp_path),
            connection={"type": "postgresql"},
        )

        functions = orchestrator.discover_and_parse_functions()
        assert len(functions) == 1
        assert "my_schema.test_func" in functions

        func = functions["my_schema.test_func"]
        assert "function_metadata" in func
        assert "code" in func
        assert func["function_metadata"]["function_name"] == "test_func"
        assert func["function_metadata"]["function_type"] == "scalar"

    def test_discover_and_parse_python_function(self, tmp_path):
        """Test discovering and parsing a Python function."""
        models_folder = tmp_path / "models"
        models_folder.mkdir()
        functions_folder = tmp_path / "functions"
        functions_folder.mkdir()
        schema_folder = functions_folder / "my_schema"
        schema_folder.mkdir()

        # Create Python function file
        python_file = schema_folder / "test_func.py"
        python_file.write_text("""
from t4t.parser.processing.function_decorator import functions

@functions.sql(
    function_name="test_func",
    return_type="FLOAT",
    description="Test function"
)
def generate_sql(adapter_type: str) -> str:
    return "CREATE FUNCTION test_func(x FLOAT) RETURNS FLOAT AS $$ SELECT x * 2.0 $$;"
""")

        orchestrator = ParserOrchestrator(
            project_folder=str(tmp_path),
            connection={"type": "duckdb"},
        )

        functions = orchestrator.discover_and_parse_functions()
        assert len(functions) == 1
        assert "my_schema.test_func" in functions

        func = functions["my_schema.test_func"]
        assert func["function_metadata"]["function_name"] == "test_func"
        assert func["needs_evaluation"] is True

    def test_discover_and_parse_function_with_metadata(self, tmp_path):
        """Test discovering function with companion metadata file."""
        models_folder = tmp_path / "models"
        models_folder.mkdir()
        functions_folder = tmp_path / "functions"
        functions_folder.mkdir()
        schema_folder = functions_folder / "my_schema"
        schema_folder.mkdir()

        # Create SQL function file
        sql_file = schema_folder / "test_func.sql"
        sql_file.write_text("""
        CREATE FUNCTION test_func(x DOUBLE) RETURNS DOUBLE AS $$
            SELECT x * 2.0
        $$;
        """)

        # Create companion metadata file
        metadata_file = schema_folder / "test_func.py"
        metadata_file.write_text("""
from t4t.typing.metadata import FunctionMetadata

metadata: FunctionMetadata = {
    "function_name": "test_func",
    "description": "Test function with metadata",
    "tags": ["test", "utility"]
}
""")

        orchestrator = ParserOrchestrator(
            project_folder=str(tmp_path),
            connection={"type": "postgresql"},
        )

        functions = orchestrator.discover_and_parse_functions()
        assert len(functions) == 1

        func = functions["my_schema.test_func"]
        assert func["function_metadata"]["description"] == "Test function with metadata"
        assert func["function_metadata"]["tags"] == ["test", "utility"]

    def test_function_caching(self, tmp_path):
        """Test that function parsing results are cached."""
        models_folder = tmp_path / "models"
        models_folder.mkdir()
        functions_folder = tmp_path / "functions"
        functions_folder.mkdir()
        schema_folder = functions_folder / "my_schema"
        schema_folder.mkdir()

        sql_file = schema_folder / "test_func.sql"
        sql_file.write_text("CREATE FUNCTION test_func() RETURNS INT AS $$ SELECT 1 $$;")

        orchestrator = ParserOrchestrator(
            project_folder=str(tmp_path),
            connection={"type": "postgresql"},
        )

        functions1 = orchestrator.discover_and_parse_functions()
        functions2 = orchestrator.discover_and_parse_functions()

        # Should return cached result
        assert functions1 is functions2

    def test_function_qualified_name_generation(self, tmp_path):
        """Test qualified function name generation."""
        models_folder = tmp_path / "models"
        models_folder.mkdir()
        functions_folder = tmp_path / "functions"
        functions_folder.mkdir()
        schema_folder = functions_folder / "my_schema"
        schema_folder.mkdir()

        sql_file = schema_folder / "test_func.sql"
        sql_file.write_text("CREATE FUNCTION test_func() RETURNS INT AS $$ SELECT 1 $$;")

        orchestrator = ParserOrchestrator(
            project_folder=str(tmp_path),
            connection={"type": "duckdb"},
        )

        functions = orchestrator.discover_and_parse_functions()
        assert "my_schema.test_func" in functions

    def test_function_qualified_name_from_metadata(self, tmp_path):
        """Test qualified function name uses schema from metadata if available."""
        models_folder = tmp_path / "models"
        models_folder.mkdir()
        functions_folder = tmp_path / "functions"
        functions_folder.mkdir()
        schema_folder = functions_folder / "different_schema"
        schema_folder.mkdir()

        sql_file = schema_folder / "test_func.sql"
        sql_file.write_text("CREATE FUNCTION test_func() RETURNS INT AS $$ SELECT 1 $$;")

        metadata_file = schema_folder / "test_func.py"
        metadata_file.write_text("""
from t4t.typing.metadata import FunctionMetadata

metadata: FunctionMetadata = {
    "function_name": "test_func",
    "schema": "my_schema"  # Override schema from path
}
""")

        orchestrator = ParserOrchestrator(
            project_folder=str(tmp_path),
            connection={"type": "postgresql"},
        )

        functions = orchestrator.discover_and_parse_functions()
        # Should use schema from metadata, not from path
        assert "my_schema.test_func" in functions
        assert "different_schema.test_func" not in functions

    def test_multiple_functions_in_same_folder(self, tmp_path):
        """Test discovering multiple functions in the same folder."""
        models_folder = tmp_path / "models"
        models_folder.mkdir()
        functions_folder = tmp_path / "functions"
        functions_folder.mkdir()
        schema_folder = functions_folder / "my_schema"
        schema_folder.mkdir()

        # Create two function files
        func1_file = schema_folder / "func1.sql"
        func1_file.write_text("CREATE FUNCTION func1() RETURNS INT AS $$ SELECT 1 $$;")

        func2_file = schema_folder / "func2.sql"
        func2_file.write_text("CREATE FUNCTION func2() RETURNS INT AS $$ SELECT 2 $$;")

        orchestrator = ParserOrchestrator(
            project_folder=str(tmp_path),
            connection={"type": "postgresql"},
        )

        functions = orchestrator.discover_and_parse_functions()
        assert len(functions) == 2
        assert "my_schema.func1" in functions
        assert "my_schema.func2" in functions

    def test_function_standardization(self, tmp_path):
        """Test that functions are properly standardized."""
        models_folder = tmp_path / "models"
        models_folder.mkdir()
        functions_folder = tmp_path / "functions"
        functions_folder.mkdir()
        schema_folder = functions_folder / "my_schema"
        schema_folder.mkdir()

        sql_file = schema_folder / "test_func.sql"
        sql_file.write_text("CREATE FUNCTION test_func() RETURNS INT AS $$ SELECT 1 $$;")

        orchestrator = ParserOrchestrator(
            project_folder=str(tmp_path),
            connection={"type": "postgresql"},
        )

        functions = orchestrator.discover_and_parse_functions()
        func = functions["my_schema.test_func"]

        # Check standardized structure
        assert "function_metadata" in func
        assert "code" in func
        assert "function_hash" in func
        assert "file_path" in func

        # Check metadata has required fields
        metadata = func["function_metadata"]
        assert "function_name" in metadata
        assert "function_type" in metadata
        assert "language" in metadata
        assert "parameters" in metadata
        assert "tags" in metadata
        assert "object_tags" in metadata

    def test_function_parsing_error_handling(self, tmp_path):
        """Test that parsing errors don't crash the entire process."""
        models_folder = tmp_path / "models"
        models_folder.mkdir()
        functions_folder = tmp_path / "functions"
        functions_folder.mkdir()
        schema_folder = functions_folder / "my_schema"
        schema_folder.mkdir()

        # Create valid function
        valid_file = schema_folder / "valid_func.sql"
        valid_file.write_text("CREATE FUNCTION valid_func() RETURNS INT AS $$ SELECT 1 $$;")

        # Create invalid function (will cause parsing error)
        invalid_file = schema_folder / "invalid_func.sql"
        invalid_file.write_text("INVALID SQL SYNTAX HERE")

        orchestrator = ParserOrchestrator(
            project_folder=str(tmp_path),
            connection={"type": "postgresql"},
        )

        # Should not raise, but should log error and continue
        functions = orchestrator.discover_and_parse_functions()

        # Should have parsed the valid function
        assert "my_schema.valid_func" in functions
        # Invalid function should not be in results
        assert "my_schema.invalid_func" not in functions
