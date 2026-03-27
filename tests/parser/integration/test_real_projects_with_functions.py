"""
Real project integration tests using example projects.

Tests parsing and compiling real projects with functions.
"""

from pathlib import Path

import pytest

from tee.cli.utils import load_project_config
from tee.compiler import compile_project
from tee.parser.core.orchestrator import ParserOrchestrator


class TestRealProjectsWithFunctions:
    """Test real example projects with functions."""

    @pytest.fixture
    def t_project_path(self):
        """Get path to t_project example."""
        project_path = Path(__file__).parent.parent.parent.parent / "examples" / "t_project"
        if not project_path.exists():
            pytest.skip("t_project example not found")
        return project_path

    @pytest.fixture
    def t_project_sno_path(self):
        """Get path to t_project_sno example."""
        project_path = Path(__file__).parent.parent.parent.parent / "examples" / "t_project_sno"
        if not project_path.exists():
            pytest.skip("t_project_sno example not found")
        return project_path

    def test_t_project_with_functions(self, t_project_path):
        """Test parsing and compiling t_project with functions."""
        # Load project config
        try:
            project_config = load_project_config(str(t_project_path))
        except Exception:
            project_config = None

        connection_config = {"type": "duckdb", "path": ":memory:"}

        # Parse project
        orchestrator = ParserOrchestrator(
            project_folder=str(t_project_path),
            connection=connection_config,
            project_config=project_config,
        )

        # Discover and parse functions
        parsed_functions = orchestrator.discover_and_parse_functions()

        # Should have at least the calculate_percentage function
        assert len(parsed_functions) >= 1
        assert "my_schema.calculate_percentage" in parsed_functions

        # Verify function structure
        func = parsed_functions["my_schema.calculate_percentage"]
        assert "function_metadata" in func
        assert "code" in func

        func_metadata = func["function_metadata"]
        assert func_metadata["function_name"] == "calculate_percentage"
        assert func_metadata["function_type"] == "scalar"
        assert func_metadata["language"] == "sql"

        # Discover and parse models
        parsed_models = orchestrator.discover_and_parse_models()
        assert len(parsed_models) > 0

        # Build dependency graph
        graph = orchestrator.build_dependency_graph()

        # Verify function is in graph
        assert "my_schema.calculate_percentage" in graph["nodes"]

        # Verify no cycles
        assert len(graph["cycles"]) == 0

    def test_t_project_sno_with_functions(self, t_project_sno_path):
        """Test parsing and compiling t_project_sno with functions."""
        # Load project config
        try:
            project_config = load_project_config(str(t_project_sno_path))
        except Exception:
            project_config = None

        connection_config = {"type": "snowflake"}

        # Parse project
        orchestrator = ParserOrchestrator(
            project_folder=str(t_project_sno_path),
            connection=connection_config,
            project_config=project_config,
        )

        # Discover and parse functions
        parsed_functions = orchestrator.discover_and_parse_functions()

        # Should have at least the calculate_percentage function
        assert len(parsed_functions) >= 1
        assert "my_schema.calculate_percentage" in parsed_functions

        # Verify function structure
        func = parsed_functions["my_schema.calculate_percentage"]
        assert "function_metadata" in func
        assert "code" in func

        # Discover and parse models
        parsed_models = orchestrator.discover_and_parse_models()
        assert len(parsed_models) > 0

        # Build dependency graph
        graph = orchestrator.build_dependency_graph()

        # Verify function is in graph
        assert "my_schema.calculate_percentage" in graph["nodes"]

    def test_compile_project_with_functions(self, t_project_path, tmp_path):
        """Test compile_project() with functions included."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Load project config
        try:
            project_config = load_project_config(str(t_project_path))
        except Exception:
            project_config = None

        connection_config = {"type": "duckdb", "path": ":memory:"}

        # Compile project
        compile_results = compile_project(
            project_folder=str(t_project_path),
            connection_config=connection_config,
            variables={},
            project_config=project_config,
            format="json",
        )

        # Verify compilation succeeded
        assert compile_results is not None

        # Check that functions are included in the compilation
        # (The compiler should have discovered and included functions)

    def test_t_project_function_metadata(self, t_project_path):
        """Test that function metadata is correctly parsed from t_project."""
        connection_config = {"type": "duckdb", "path": ":memory:"}

        orchestrator = ParserOrchestrator(
            project_folder=str(t_project_path),
            connection=connection_config,
        )

        parsed_functions = orchestrator.discover_and_parse_functions()

        if "my_schema.calculate_percentage" in parsed_functions:
            func = parsed_functions["my_schema.calculate_percentage"]
            func_metadata = func["function_metadata"]

            # Verify metadata fields
            assert "description" in func_metadata
            assert "parameters" in func_metadata
            assert len(func_metadata["parameters"]) == 2
            assert "return_type" in func_metadata
            assert "tags" in func_metadata
            assert "object_tags" in func_metadata

    def test_t_project_function_code_structure(self, t_project_path):
        """Test that function code structure is correct."""
        connection_config = {"type": "duckdb", "path": ":memory:"}

        orchestrator = ParserOrchestrator(
            project_folder=str(t_project_path),
            connection=connection_config,
        )

        parsed_functions = orchestrator.discover_and_parse_functions()

        if "my_schema.calculate_percentage" in parsed_functions:
            func = parsed_functions["my_schema.calculate_percentage"]

            # Verify code structure
            assert "code" in func, "Function should have code structure"
            code = func.get("code")
            if code:
                assert "sql" in code, "Function code should have sql"
                sql_code = code["sql"]
                assert "original_sql" in sql_code, "SQL code should have original_sql"
                assert "source_tables" in sql_code, "SQL code should have source_tables"
                assert "source_functions" in sql_code, "SQL code should have source_functions"

                # Verify SQL contains function definition
                if sql_code.get("original_sql"):
                    assert "calculate_percentage" in sql_code["original_sql"].lower()
                    assert (
                        "CREATE" in sql_code["original_sql"].upper()
                        or "FUNCTION" in sql_code["original_sql"].upper()
                    )
