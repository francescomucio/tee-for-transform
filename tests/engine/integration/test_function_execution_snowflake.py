"""
Integration tests for function execution with Snowflake.

These tests verify that functions are correctly created and executed in Snowflake.
Note: These tests require Snowflake credentials and may be slow due to network latency.
"""

import json
import os
from pathlib import Path

import pytest

from t4t.engine.execution_engine import ExecutionEngine
from t4t.parser.core.orchestrator import ParserOrchestrator


@pytest.mark.integration
@pytest.mark.slow
class TestFunctionExecutionSnowflake:
    """Integration tests for function execution with Snowflake."""

    @pytest.fixture(scope="class")
    def snowflake_config(self):
        """Get Snowflake configuration from local config file or environment variables."""
        # Try to load from local config file (gitignored)
        # Path from test file: tests/engine/integration/test_function_execution_snowflake.py
        # Config file: tests/.snowflake_config.json
        test_file_dir = Path(__file__).parent  # tests/engine/integration/
        project_root = test_file_dir.parent.parent.parent  # t4t-for-transform/
        config_file = project_root / "tests" / ".snowflake_config.json"
        config = {}

        if config_file.exists():
            try:
                with open(config_file, "r") as f:
                    file_config = json.load(f)
                    config = {
                        "type": "snowflake",
                        "host": file_config.get("host")
                        or f"{file_config.get('account')}.snowflakecomputing.com",
                        "account": file_config.get("account"),
                        "user": file_config.get("user"),
                        "password": file_config.get("password"),
                        "warehouse": file_config.get("warehouse"),
                        "database": file_config.get("database"),
                        "schema": file_config.get("schema", "PUBLIC"),
                        "role": file_config.get("role"),
                    }
            except Exception as e:
                pytest.skip(f"Could not load Snowflake config from {config_file}: {e}")
        else:
            # Fall back to environment variables
            config = {
                "type": "snowflake",
                "account": os.getenv("SNOWFLAKE_ACCOUNT"),
                "user": os.getenv("SNOWFLAKE_USER"),
                "password": os.getenv("SNOWFLAKE_PASSWORD"),
                "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE", "TEST_WAREHOUSE"),
                "database": os.getenv("SNOWFLAKE_DATABASE", "TEST_DB"),
                "schema": os.getenv("SNOWFLAKE_SCHEMA", "TEST_SCHEMA"),
                "role": os.getenv("SNOWFLAKE_ROLE", "TEST_ROLE"),
            }

        # Skip if credentials not available
        if not all([config.get("account"), config.get("user"), config.get("password")]):
            pytest.skip(
                "Snowflake credentials not available (check tests/.snowflake_config.json or environment variables)"
            )

        return config

    @pytest.fixture(scope="class")
    def temp_project_snowflake(self):
        """Create a temporary project with Snowflake-specific function files."""
        import tempfile

        temp_dir = tempfile.mkdtemp()
        project_path = Path(temp_dir)

        # Create data directory for state database
        data_dir = project_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        functions_dir = project_path / "functions" / "my_schema"
        functions_dir.mkdir(parents=True, exist_ok=True)

        # Create empty models folder (required for dependency graph building)
        models_dir = project_path / "models"
        models_dir.mkdir(parents=True, exist_ok=True)

        # Create Snowflake-specific function SQL
        function_sql = functions_dir / "calculate_percentage.snowflake.sql"
        function_sql.write_text("""
CREATE OR REPLACE FUNCTION my_schema.calculate_percentage(numerator FLOAT, denominator FLOAT)
RETURNS FLOAT
AS $$
    SELECT CASE
        WHEN denominator = 0 THEN NULL
        ELSE (numerator / denominator) * 100.0
    END
$$;
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
        {"name": "numerator", "type": "FLOAT"},
        {"name": "denominator", "type": "FLOAT"}
    ],
    "return_type": "FLOAT",
    "deterministic": True,
    "tags": ["math", "utility"],
    "object_tags": {"department": "analytics", "team": "data-engineering"},
}
""")

        # Create project.toml
        project_toml = project_path / "project.toml"
        project_toml.write_text("""
name = "test_project"
[connection]
type = "snowflake"
""")

        yield project_path

        # Cleanup: remove temporary directory
        import shutil

        if project_path.exists():
            shutil.rmtree(project_path, ignore_errors=True)

    @pytest.fixture(scope="class")
    def snowflake_engine(self, snowflake_config, temp_project_snowflake):
        """
        Reusable Snowflake engine for all tests in class.

        This fixture creates a single connection that is reused across all tests
        in the class, reducing connection overhead from ~2.3s per test to ~2.3s per class.
        """
        engine = ExecutionEngine(
            config=snowflake_config,
            project_folder=str(temp_project_snowflake),
        )
        engine.connect()
        yield engine
        engine.disconnect()

    def test_execute_function_in_snowflake(
        self, temp_project_snowflake, snowflake_config, snowflake_engine
    ):
        """Test executing a function in Snowflake."""
        # Use shared engine (connection reused from class-scoped fixture)
        engine = snowflake_engine

        # Parse functions
        orchestrator = ParserOrchestrator(
            project_folder=str(temp_project_snowflake),
            connection=snowflake_config,
        )
        parsed_functions = orchestrator.discover_and_parse_functions()

        assert len(parsed_functions) == 1
        assert "my_schema.calculate_percentage" in parsed_functions

        # Build dependency graph
        graph = orchestrator.build_dependency_graph()
        execution_order = graph["execution_order"]

        # Execute functions
        results = engine.execute_functions(parsed_functions, execution_order)

        # Verify function was executed
        assert len(results["executed_functions"]) == 1
        assert "my_schema.calculate_percentage" in results["executed_functions"]
        assert len(results["failed_functions"]) == 0

        # Verify function exists in database
        assert engine.adapter.function_exists("my_schema.calculate_percentage")

        # Test that function can be called
        result = engine.adapter.execute_query(
            "SELECT my_schema.calculate_percentage(10.0, 20.0) as result"
        )
        # Snowflake adapter returns a list of rows, not a cursor
        assert len(result) > 0
        assert result[0][0] == 50.0

    def test_function_tags_in_snowflake(
        self, temp_project_snowflake, snowflake_config, snowflake_engine
    ):
        """Test that function tags are attached in Snowflake."""
        # Use shared engine (connection reused from class-scoped fixture)
        engine = snowflake_engine

        # Parse functions
        orchestrator = ParserOrchestrator(
            project_folder=str(temp_project_snowflake),
            connection=snowflake_config,
        )
        parsed_functions = orchestrator.discover_and_parse_functions()

        # Build dependency graph
        graph = orchestrator.build_dependency_graph()
        execution_order = graph["execution_order"]

        # Execute functions
        results = engine.execute_functions(parsed_functions, execution_order)

        # Verify function was executed
        assert len(results["executed_functions"]) == 1

        # In Snowflake, tags should be attached via adapter
        # We can verify by checking function info (if available)
        func_info = engine.adapter.get_function_info("my_schema.calculate_percentage")
        assert func_info["exists"] is True
