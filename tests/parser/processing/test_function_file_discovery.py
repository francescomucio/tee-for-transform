"""
Tests for function file discovery.
"""

import tempfile
from pathlib import Path


from t4t.parser.processing.file_discovery import FileDiscovery


class TestFunctionFileDiscovery:
    """Test function file discovery functionality."""

    def test_discover_function_files_missing_folder(self):
        """Test that missing functions folder returns empty lists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            models_folder = Path(tmpdir) / "models"
            models_folder.mkdir(parents=True, exist_ok=True)
            functions_folder = Path(tmpdir) / "functions"
            discovery = FileDiscovery(models_folder, functions_folder)

            result = discovery.discover_function_files()

            assert result["sql"] == []
            assert result["python"] == []
            assert result["database_overrides"] == []

    def test_discover_function_files_flat_structure(self):
        """Test discovery of flat structure: functions/{schema}/{function_name}.sql"""
        with tempfile.TemporaryDirectory() as tmpdir:
            functions_folder = Path(tmpdir) / "functions"
            schema_folder = functions_folder / "my_schema"
            schema_folder.mkdir(parents=True, exist_ok=True)

            # Create function files
            (schema_folder / "calculate_metric.sql").write_text("CREATE FUNCTION ...")
            (schema_folder / "helper_func.py").write_text("# Python function")

            models_folder = Path(tmpdir) / "models"
            models_folder.mkdir(exist_ok=True)
            discovery = FileDiscovery(models_folder, functions_folder)

            result = discovery.discover_function_files()

            assert len(result["sql"]) == 1
            assert len(result["python"]) == 1
            assert len(result["database_overrides"]) == 0
            assert any("calculate_metric.sql" in str(f) for f in result["sql"])
            assert any("helper_func.py" in str(f) for f in result["python"])

    def test_discover_function_files_folder_structure(self):
        """Test discovery of folder structure: functions/{schema}/{function_name}/{function_name}.sql"""
        with tempfile.TemporaryDirectory() as tmpdir:
            functions_folder = Path(tmpdir) / "functions"
            schema_folder = functions_folder / "my_schema"
            function_folder = schema_folder / "complex_function"
            function_folder.mkdir(parents=True, exist_ok=True)

            # Create function files in folder
            (function_folder / "complex_function.sql").write_text("CREATE FUNCTION ...")
            (function_folder / "complex_function.py").write_text("# Metadata")

            models_folder = Path(tmpdir) / "models"
            models_folder.mkdir(exist_ok=True)
            discovery = FileDiscovery(models_folder, functions_folder)

            result = discovery.discover_function_files()

            assert len(result["sql"]) == 1
            assert len(result["python"]) == 1
            assert any("complex_function.sql" in str(f) for f in result["sql"])
            assert any("complex_function.py" in str(f) for f in result["python"])

    def test_discover_function_files_database_overrides(self):
        """Test discovery of database override files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            functions_folder = Path(tmpdir) / "functions"
            schema_folder = functions_folder / "my_schema"
            schema_folder.mkdir(parents=True, exist_ok=True)

            # Create database override files
            (schema_folder / "calculate_metric.postgresql.sql").write_text("CREATE FUNCTION ...")
            (schema_folder / "complex_func.snowflake.js").write_text("// JavaScript UDF")
            (schema_folder / "helper_func.duckdb.sql").write_text("CREATE FUNCTION ...")

            # Regular function file (not an override)
            (schema_folder / "regular_func.sql").write_text("CREATE FUNCTION ...")

            models_folder = Path(tmpdir) / "models"
            models_folder.mkdir(exist_ok=True)
            discovery = FileDiscovery(models_folder, functions_folder)

            result = discovery.discover_function_files()

            assert len(result["database_overrides"]) == 3
            assert len(result["sql"]) == 1  # Only regular_func.sql, not the overrides
            assert any(
                "calculate_metric.postgresql.sql" in str(f) for f in result["database_overrides"]
            )
            assert any("complex_func.snowflake.js" in str(f) for f in result["database_overrides"])
            assert any("helper_func.duckdb.sql" in str(f) for f in result["database_overrides"])
            assert any("regular_func.sql" in str(f) for f in result["sql"])

    def test_discover_function_files_mixed_structures(self):
        """Test discovery with mixed flat and folder structures."""
        with tempfile.TemporaryDirectory() as tmpdir:
            functions_folder = Path(tmpdir) / "functions"

            # Flat structure
            schema1 = functions_folder / "schema1"
            schema1.mkdir(parents=True, exist_ok=True)
            (schema1 / "flat_func.sql").write_text("CREATE FUNCTION ...")

            # Folder structure
            schema2 = functions_folder / "schema2"
            func_folder = schema2 / "folder_func"
            func_folder.mkdir(parents=True, exist_ok=True)
            (func_folder / "folder_func.sql").write_text("CREATE FUNCTION ...")

            models_folder = Path(tmpdir) / "models"
            models_folder.mkdir(exist_ok=True)
            discovery = FileDiscovery(models_folder, functions_folder)

            result = discovery.discover_function_files()

            assert len(result["sql"]) == 2
            assert any("flat_func.sql" in str(f) for f in result["sql"])
            assert any("folder_func.sql" in str(f) for f in result["sql"])

    def test_discover_function_files_caching(self):
        """Test that function file discovery results are cached."""
        with tempfile.TemporaryDirectory() as tmpdir:
            functions_folder = Path(tmpdir) / "functions"
            schema_folder = functions_folder / "my_schema"
            schema_folder.mkdir(parents=True, exist_ok=True)

            (schema_folder / "test_func.sql").write_text("CREATE FUNCTION ...")

            models_folder = Path(tmpdir) / "models"
            models_folder.mkdir(exist_ok=True)
            discovery = FileDiscovery(models_folder, functions_folder)

            # First call
            result1 = discovery.discover_function_files()

            # Add a new file
            (schema_folder / "new_func.sql").write_text("CREATE FUNCTION ...")

            # Second call should return cached result (same files)
            result2 = discovery.discover_function_files()

            assert len(result1["sql"]) == len(result2["sql"]) == 1
            # Results should be the same (cached)
            assert result1["sql"] == result2["sql"]

    def test_discover_function_files_cache_clear(self):
        """Test that cache clearing works for function files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            functions_folder = Path(tmpdir) / "functions"
            schema_folder = functions_folder / "my_schema"
            schema_folder.mkdir(parents=True, exist_ok=True)

            (schema_folder / "test_func.sql").write_text("CREATE FUNCTION ...")

            models_folder = Path(tmpdir) / "models"
            models_folder.mkdir(exist_ok=True)
            discovery = FileDiscovery(models_folder, functions_folder)

            # First call
            result1 = discovery.discover_function_files()

            # Clear cache
            discovery.clear_cache()

            # Add a new file
            (schema_folder / "new_func.sql").write_text("CREATE FUNCTION ...")

            # Second call after cache clear should discover new file
            result2 = discovery.discover_function_files()

            assert len(result1["sql"]) == 1
            assert len(result2["sql"]) == 2

    def test_discover_function_files_empty_folder(self):
        """Test discovery of empty functions folder."""
        with tempfile.TemporaryDirectory() as tmpdir:
            functions_folder = Path(tmpdir) / "functions"
            functions_folder.mkdir(parents=True, exist_ok=True)

            models_folder = Path(tmpdir) / "models"
            models_folder.mkdir(exist_ok=True)
            discovery = FileDiscovery(models_folder, functions_folder)

            result = discovery.discover_function_files()

            assert result["sql"] == []
            assert result["python"] == []
            assert result["database_overrides"] == []

    def test_discover_function_files_nested_schemas(self):
        """Test discovery with nested schema structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            functions_folder = Path(tmpdir) / "functions"

            # Multiple schema levels
            schema1 = functions_folder / "schema1"
            schema1.mkdir(parents=True, exist_ok=True)
            (schema1 / "func1.sql").write_text("CREATE FUNCTION ...")

            schema2 = functions_folder / "schema2"
            schema2.mkdir(parents=True, exist_ok=True)
            (schema2 / "func2.sql").write_text("CREATE FUNCTION ...")

            models_folder = Path(tmpdir) / "models"
            models_folder.mkdir(exist_ok=True)
            discovery = FileDiscovery(models_folder, functions_folder)

            result = discovery.discover_function_files()

            assert len(result["sql"]) == 2
            assert any("schema1" in str(f) and "func1.sql" in str(f) for f in result["sql"])
            assert any("schema2" in str(f) and "func2.sql" in str(f) for f in result["sql"])

    def test_discover_function_files_sorted_results(self):
        """Test that discovered files are sorted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            functions_folder = Path(tmpdir) / "functions"
            schema_folder = functions_folder / "my_schema"
            schema_folder.mkdir(parents=True, exist_ok=True)

            # Create files in non-alphabetical order
            (schema_folder / "z_func.sql").write_text("CREATE FUNCTION ...")
            (schema_folder / "a_func.sql").write_text("CREATE FUNCTION ...")
            (schema_folder / "m_func.sql").write_text("CREATE FUNCTION ...")

            models_folder = Path(tmpdir) / "models"
            models_folder.mkdir(exist_ok=True)
            discovery = FileDiscovery(models_folder, functions_folder)

            result = discovery.discover_function_files()

            assert len(result["sql"]) == 3
            # Check that results are sorted
            file_names = [f.name for f in result["sql"]]
            assert file_names == sorted(file_names)
