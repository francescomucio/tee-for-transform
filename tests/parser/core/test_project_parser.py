from pathlib import Path

from tee.parser import ProjectParser
from tee.parser.analysis import TableResolver


class TestProjectParser:
    """Test cases for ProjectParser class."""

    def test_generate_full_table_name_duckdb(self):
        """Test _generate_full_table_name method for DuckDB connections."""
        # Create a table resolver with DuckDB connection
        table_resolver = TableResolver({"type": "duckdb"})
        models_folder = Path("test_project/models")

        # Test case 1: File in schema subfolder
        sql_file = Path("test_project/models/my_schema/my_table.sql")
        result = table_resolver.generate_full_table_name(sql_file, models_folder)
        assert result == "my_schema.my_table"

        # Test case 2: File directly in models folder
        sql_file = Path("test_project/models/direct_table.sql")
        result = table_resolver.generate_full_table_name(sql_file, models_folder)
        assert result == "direct_table"

        # Test case 3: File in nested schema folder
        sql_file = Path("test_project/models/schema1/schema2/deep_table.sql")
        result = table_resolver.generate_full_table_name(sql_file, models_folder)
        assert result == "schema1.deep_table"

    def test_generate_full_table_name_non_duckdb(self):
        """Test _generate_full_table_name method for non-DuckDB connections."""
        # Create a table resolver with PostgreSQL connection
        table_resolver = TableResolver({"type": "postgresql"})
        models_folder = Path("test_project/models")

        # Test case 1: File in schema subfolder
        sql_file = Path("test_project/models/my_schema/my_table.sql")
        result = table_resolver.generate_full_table_name(sql_file, models_folder)
        assert result == "my_schema.my_table"

        # Test case 2: File directly in models folder
        sql_file = Path("test_project/models/direct_table.sql")
        result = table_resolver.generate_full_table_name(sql_file, models_folder)
        assert result == "direct_table"

        # Test case 3: File in nested schema folder
        sql_file = Path("test_project/models/schema1/schema2/deep_table.sql")
        result = table_resolver.generate_full_table_name(sql_file, models_folder)
        assert result == "schema1.schema2.deep_table"

    def test_generate_full_table_name_snowflake(self):
        """Test _generate_full_table_name method for Snowflake connections."""
        # Create a table resolver with Snowflake connection
        table_resolver = TableResolver({"type": "snowflake"})
        models_folder = Path("test_project/models")

        # Test case 1: SQL file in schema subfolder
        sql_file = Path("test_project/models/my_schema/my_table.sql")
        result = table_resolver.generate_full_table_name(sql_file, models_folder)
        assert result == "my_schema.my_table"

        # Test case 2: Python file in schema subfolder (the bug we fixed)
        python_file = Path("test_project/models/my_schema/my_auto_tables.py")
        result = table_resolver.generate_full_table_name(python_file, models_folder)
        assert result == "my_schema.my_auto_tables"  # Should NOT include .py extension

        # Test case 3: Python file directly in models folder
        python_file = Path("test_project/models/direct_python_model.py")
        result = table_resolver.generate_full_table_name(python_file, models_folder)
        assert result == "direct_python_model"  # Should NOT include .py extension

        # Test case 4: File in nested schema folder
        sql_file = Path("test_project/models/schema1/schema2/deep_table.sql")
        result = table_resolver.generate_full_table_name(sql_file, models_folder)
        assert result == "schema1.schema2.deep_table"

    def test_generate_full_table_name_python_files(self):
        """Test _generate_full_table_name method with Python files for different database types."""
        models_folder = Path("test_project/models")

        # Test DuckDB with Python files
        duckdb_resolver = TableResolver({"type": "duckdb"})
        python_file = Path("test_project/models/my_schema/my_auto_tables.py")
        result = duckdb_resolver.generate_full_table_name(python_file, models_folder)
        assert (
            result == "my_schema.my_auto_tables"
        )  # DuckDB uses .stem which removes all extensions

        # Test Snowflake with Python files
        snowflake_resolver = TableResolver({"type": "snowflake"})
        result = snowflake_resolver.generate_full_table_name(python_file, models_folder)
        assert result == "my_schema.my_auto_tables"  # Should match DuckDB behavior after fix

        # Test PostgreSQL with Python files
        postgresql_resolver = TableResolver({"type": "postgresql"})
        result = postgresql_resolver.generate_full_table_name(python_file, models_folder)
        assert result == "my_schema.my_auto_tables"  # Should match DuckDB behavior after fix

    def test_generate_full_table_name_edge_cases(self):
        """Test _generate_full_table_name method with edge cases."""
        table_resolver = TableResolver({"type": "duckdb"})
        models_folder = Path("test_project/models")

        # Test case 1: File with different extension
        sql_file = Path("test_project/models/my_schema/my_table.txt")
        result = table_resolver.generate_full_table_name(sql_file, models_folder)
        assert result == "my_schema.my_table"

        # Test case 2: File with multiple dots in name
        sql_file = Path("test_project/models/my_schema/my.table.sql")
        result = table_resolver.generate_full_table_name(sql_file, models_folder)
        assert result == "my_schema.my.table"

        # Test case 3: File with underscores in schema name
        sql_file = Path("test_project/models/my_schema_name/my_table.sql")
        result = table_resolver.generate_full_table_name(sql_file, models_folder)
        assert result == "my_schema_name.my_table"

    def test_generate_full_table_name_extension_removal(self):
        """Test that all file extensions are properly removed for non-DuckDB databases."""
        models_folder = Path("test_project/models")

        # Test various file extensions with Snowflake
        snowflake_resolver = TableResolver({"type": "snowflake"})

        test_cases = [
            ("my_schema/my_table.sql", "my_schema.my_table"),
            ("my_schema/my_table.py", "my_schema.my_table"),
            ("my_schema/my_table.txt", "my_schema.my_table"),
            ("my_schema/my_table.csv", "my_schema.my_table"),
            ("my_schema/my_table.json", "my_schema.my_table"),
            ("my_schema/my_table.yaml", "my_schema.my_table"),
            ("my_schema/my_table.yml", "my_schema.my_table"),
        ]

        for file_path, expected in test_cases:
            sql_file = Path(f"test_project/models/{file_path}")
            result = snowflake_resolver.generate_full_table_name(sql_file, models_folder)
            assert result == expected, f"Failed for {file_path}: got {result}, expected {expected}"

        # Test that DuckDB behavior is unchanged (uses .stem)
        duckdb_resolver = TableResolver({"type": "duckdb"})
        for file_path, expected in test_cases:
            sql_file = Path(f"test_project/models/{file_path}")
            result = duckdb_resolver.generate_full_table_name(sql_file, models_folder)
            assert result == expected, (
                f"DuckDB failed for {file_path}: got {result}, expected {expected}"
            )

    def test_generate_full_table_name_windows_paths(self):
        """Test _generate_full_table_name method with Windows-style paths."""
        table_resolver = TableResolver({"type": "duckdb"})
        models_folder = Path("test_project/models")

        # Test case: Windows-style path separators (Path normalizes these)
        sql_file = Path("test_project/models/my_schema/my_table.sql")
        result = table_resolver.generate_full_table_name(sql_file, models_folder)
        assert result == "my_schema.my_table"

        # Test case: Mixed separators (Path handles this automatically)
        sql_file = Path("test_project") / "models" / "my_schema" / "my_table.sql"
        result = table_resolver.generate_full_table_name(sql_file, models_folder)
        assert result == "my_schema.my_table"

    def test_generate_full_table_name_connection_type_none(self):
        """Test _generate_full_table_name method when connection type is None."""
        table_resolver = TableResolver({"type": None})
        models_folder = Path("test_project/models")

        sql_file = Path("test_project/models/my_schema/my_table.sql")
        result = table_resolver.generate_full_table_name(sql_file, models_folder)
        assert result == "my_schema.my_table"

    def test_generate_full_table_name_connection_type_missing(self):
        """Test _generate_full_table_name method when connection type is missing."""
        table_resolver = TableResolver({})
        models_folder = Path("test_project/models")

        sql_file = Path("test_project/models/my_schema/my_table.sql")
        result = table_resolver.generate_full_table_name(sql_file, models_folder)
        assert result == "my_schema.my_table"

    def test_project_parser_initialization(self):
        """Test ProjectParser initialization."""
        parser = ProjectParser("test_project", {"type": "duckdb"})

        assert parser.project_folder == Path("test_project")
        assert parser.connection == {"type": "duckdb"}
        assert parser.models_folder == Path("test_project/models")

    def test_project_parser_with_variables(self):
        """Test ProjectParser initialization with variables."""
        variables = {"env": "production", "debug": True}
        parser = ProjectParser("test_project", {"type": "duckdb"}, variables)

        assert parser.variables == variables

    def test_table_resolver_resolve_table_reference(self):
        """Test table reference resolution."""
        table_resolver = TableResolver({"type": "duckdb"})

        # Mock parsed models
        parsed_models = {
            "schema1.table1": {"code": {"sql": {"source_tables": ["table2"]}}},
            "schema1.table2": {"code": {"sql": {"source_tables": []}}},
            "schema2.table3": {"code": {"sql": {"source_tables": ["table1"]}}},
        }

        # Test direct match
        result = table_resolver.resolve_table_reference("schema1.table1", parsed_models)
        assert result == "schema1.table1"

        # Test partial match
        result = table_resolver.resolve_table_reference("table1", parsed_models)
        assert result == "schema1.table1"

        # Test no match
        result = table_resolver.resolve_table_reference("nonexistent", parsed_models)
        assert result is None
