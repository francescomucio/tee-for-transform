"""
Unit tests for the compiler module.
"""

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest
import yaml

from t4t.compiler import CompilationError, _merge_test_libraries, compile_project


class TestCompileProject:
    """Test cases for compile_project function."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def mock_connection_config(self):
        """Create mock connection configuration."""
        return {
            "type": "duckdb",
            "path": ":memory:",
        }

    def _setup_project(
        self, temp_dir: Path, models_sql: dict[str, str], connection_config: dict[str, Any]
    ) -> Path:
        """Helper to set up a project structure."""
        models_dir = temp_dir / "models"
        models_dir.mkdir(parents=True, exist_ok=True)

        project_toml = temp_dir / "project.toml"
        path_config = (
            f'path = "{connection_config.get("path", ":memory:")}"'
            if "path" in connection_config
            else ""
        )
        project_toml.write_text(
            f'name = "test_project"\n[connection]\ntype = "{connection_config["type"]}"\n{path_config}\n'
        )

        for table_name, sql in models_sql.items():
            if "." in table_name:
                schema, table = table_name.split(".", 1)
                schema_dir = models_dir / schema
                schema_dir.mkdir(exist_ok=True)
                model_file = schema_dir / f"{table}.sql"
            else:
                model_file = models_dir / f"{table_name}.sql"
            model_file.write_text(sql)

        return temp_dir

    def test_compile_project_basic(self, temp_dir, mock_connection_config):
        """Test basic compilation with SQL models."""
        models_sql = {
            "schema1.table1": "SELECT 1 as id, 'test' as name",
        }
        project_path = self._setup_project(temp_dir, models_sql, mock_connection_config)

        results = compile_project(
            project_folder=str(project_path),
            connection_config=mock_connection_config,
            variables={},
            project_config={
                "name": "test_project",
                "project_folder": "test_project",
                "connection": mock_connection_config,
            },
        )

        assert results["success"] is True
        assert results["parsed_models_count"] == 1
        assert results["imported_ots_count"] == 0
        assert results["total_transformations"] == 1
        assert results["ots_modules_count"] == 1

        # Check that OTS module was created
        output_folder = project_path / "output" / "ots_modules"
        ots_files = list(output_folder.glob("*.ots.json"))
        assert len(ots_files) == 1

    def test_compile_project_with_imported_ots(self, temp_dir, mock_connection_config):
        """Test compilation with imported OTS modules."""
        models_sql = {
            "schema1.table1": "SELECT 1 as id, 'test' as name",
        }
        project_path = self._setup_project(temp_dir, models_sql, mock_connection_config)

        # Create an imported OTS module
        models_dir = project_path / "models"
        schema_dir = models_dir / "schema2"
        schema_dir.mkdir(exist_ok=True)

        imported_ots = {
            "ots_version": "0.1.0",
            "module_name": "test_project.schema2",
            "target": {
                "database": "test_project",
                "schema": "schema2",
                "sql_dialect": "duckdb",
            },
            "transformations": [
                {
                    "transformation_id": "schema2.table2",
                    "description": "Imported table",
                    "transformation_type": "sql",
                    "sql_dialect": "duckdb",
                    "code": {
                        "sql": {
                            "original_sql": "SELECT 2 as id, 'imported' as name",
                            "operation_type": "select",
                        }
                    },
                    "schema": [],
                    "materialization": {"type": "table"},
                    "metadata": {},
                }
            ],
        }

        ots_file = schema_dir / "schema2.ots.json"
        with open(ots_file, "w") as f:
            json.dump(imported_ots, f)

        results = compile_project(
            project_folder=str(project_path),
            connection_config=mock_connection_config,
            variables={},
            project_config={
                "name": "test_project",
                "project_folder": "test_project",
                "connection": mock_connection_config,
            },
        )

        assert results["success"] is True
        assert results["parsed_models_count"] == 1
        assert results["imported_ots_count"] == 1
        assert results["total_transformations"] == 2
        assert results["ots_modules_count"] == 2  # One for each schema

    def test_compile_project_conflict_detection(self, temp_dir, mock_connection_config):
        """Test that conflicts are detected when transformation_id overlaps."""
        models_sql = {
            "schema1.table1": "SELECT 1 as id, 'test' as name",
        }
        project_path = self._setup_project(temp_dir, models_sql, mock_connection_config)

        # Create an imported OTS module with conflicting transformation_id
        models_dir = project_path / "models"
        schema_dir = models_dir / "schema1"
        schema_dir.mkdir(exist_ok=True)

        imported_ots = {
            "ots_version": "0.1.0",
            "module_name": "test_project.schema1",
            "target": {
                "database": "test_project",
                "schema": "schema1",
                "sql_dialect": "duckdb",
            },
            "transformations": [
                {
                    "transformation_id": "schema1.table1",  # Conflict!
                    "description": "Imported table",
                    "transformation_type": "sql",
                    "sql_dialect": "duckdb",
                    "code": {
                        "sql": {
                            "original_sql": "SELECT 2 as id",
                            "operation_type": "select",
                        }
                    },
                    "schema": [],
                    "materialization": {"type": "table"},
                    "metadata": {},
                }
            ],
        }

        ots_file = schema_dir / "schema1.ots.json"
        with open(ots_file, "w") as f:
            json.dump(imported_ots, f)

        with pytest.raises(CompilationError, match="duplicate transformation_id"):
            compile_project(
                project_folder=str(project_path),
                connection_config=mock_connection_config,
                variables={},
                project_config={"name": "test_project", "connection": mock_connection_config},
            )

    def test_compile_project_yaml_export(self, temp_dir, mock_connection_config):
        """Test compilation with YAML export format."""
        models_sql = {
            "schema1.table1": "SELECT 1 as id, 'test' as name",
        }
        project_path = self._setup_project(temp_dir, models_sql, mock_connection_config)

        results = compile_project(
            project_folder=str(project_path),
            connection_config=mock_connection_config,
            variables={},
            project_config={
                "name": "test_project",
                "project_folder": "test_project",
                "connection": mock_connection_config,
            },
            format="yaml",
        )

        assert results["success"] is True

        # Check that YAML files were created
        output_folder = project_path / "output" / "ots_modules"
        yaml_files = list(output_folder.glob("*.ots.yaml"))
        json_files = list(output_folder.glob("*.ots.json"))

        assert len(yaml_files) == 1
        assert len(json_files) == 0

        # Verify YAML is valid
        with open(yaml_files[0]) as f:
            yaml_data = yaml.safe_load(f)
            assert yaml_data["ots_version"] == "0.2.2"
            assert yaml_data["module_name"] == "test_project.schema1"


class TestMergeTestLibraries:
    """Test cases for _merge_test_libraries function."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_merge_test_libraries_project_only(self, temp_dir):
        """Test merging when only project has test library."""
        project_path = temp_dir
        tests_folder = project_path / "tests"
        tests_folder.mkdir()
        output_folder = project_path / "output" / "ots_modules"
        output_folder.mkdir(parents=True)

        # Create a test file
        test_file = tests_folder / "test_minimum_rows.sql"
        test_file.write_text("""
-- Check minimum rows
SELECT 1 as violation
FROM @table_name
GROUP BY 1
HAVING COUNT(*) < @min_rows:10
""")

        project_config = {"name": "test_project"}
        imported_ots_modules = []

        result = _merge_test_libraries(
            project_path, tests_folder, output_folder, project_config, imported_ots_modules
        )

        assert result is not None
        assert result.exists()

        # Verify test library content
        with open(result) as f:
            test_lib = json.load(f)
            assert "generic_tests" in test_lib
            assert "test_minimum_rows" in test_lib["generic_tests"]  # Test name comes from filename

    def test_merge_test_libraries_with_imported(self, temp_dir):
        """Test merging project and imported test libraries."""
        project_path = temp_dir
        tests_folder = project_path / "tests"
        tests_folder.mkdir()
        output_folder = project_path / "output" / "ots_modules"
        output_folder.mkdir(parents=True)

        # Create project test
        test_file = tests_folder / "test_minimum_rows.sql"
        test_file.write_text("""
SELECT 1 as violation
FROM @table_name
GROUP BY 1
HAVING COUNT(*) < @min_rows:10
""")

        # Create imported OTS module with test library reference
        models_dir = project_path / "models" / "schema1"
        models_dir.mkdir(parents=True)

        imported_test_lib = {
            "test_library_version": "1.0",
            "description": "Imported test library",
            "generic_tests": {
                "test_unique": {
                    "type": "sql",
                    "level": "column",
                    "description": "Check uniqueness",
                    "sql": "SELECT @column_name FROM @table_name GROUP BY @column_name HAVING COUNT(*) > 1",
                    "parameters": [],
                }
            },
        }

        imported_test_lib_file = models_dir / "imported_test_library.ots.json"
        with open(imported_test_lib_file, "w") as f:
            json.dump(imported_test_lib, f)

        imported_ots_module = {
            "ots_version": "0.1.0",
            "module_name": "test_project.schema1",
            "target": {
                "database": "test_project",
                "schema": "schema1",
                "sql_dialect": "duckdb",
            },
            "test_library_path": "imported_test_library.ots.json",
            "transformations": [],
        }

        ots_file = models_dir / "schema1.ots.json"
        with open(ots_file, "w") as f:
            json.dump(imported_ots_module, f)

        project_config = {"name": "test_project"}
        imported_ots_modules = [(imported_ots_module, ots_file)]

        result = _merge_test_libraries(
            project_path, tests_folder, output_folder, project_config, imported_ots_modules
        )

        assert result is not None
        assert result.exists()

        # Verify merged test library
        with open(result) as f:
            merged_lib = json.load(f)
            assert "generic_tests" in merged_lib
            assert (
                "test_minimum_rows" in merged_lib["generic_tests"]
            )  # From project (filename-based)
            assert "test_unique" in merged_lib["generic_tests"]  # From imported

    def test_merge_test_libraries_conflict_resolution(self, temp_dir):
        """Test that conflicts are resolved (project takes precedence)."""
        project_path = temp_dir
        tests_folder = project_path / "tests"
        tests_folder.mkdir()
        output_folder = project_path / "output" / "ots_modules"
        output_folder.mkdir(parents=True)

        # Create project test
        test_file = tests_folder / "test_conflict.sql"
        test_file.write_text("""
-- Project version
SELECT 1 as violation FROM @table_name
""")

        # Create imported test library with same test name
        models_dir = project_path / "models" / "schema1"
        models_dir.mkdir(parents=True)

        imported_test_lib = {
            "test_library_version": "1.0",
            "generic_tests": {
                "test_conflict": {
                    "type": "sql",
                    "level": "table",
                    "description": "Imported version",
                    "sql": "SELECT 2 as violation FROM @table_name",
                    "parameters": [],
                }
            },
        }

        imported_test_lib_file = models_dir / "imported_test_library.ots.json"
        with open(imported_test_lib_file, "w") as f:
            json.dump(imported_test_lib, f)

        imported_ots_module = {
            "ots_version": "0.1.0",
            "module_name": "test_project.schema1",
            "target": {
                "database": "test_project",
                "schema": "schema1",
                "sql_dialect": "duckdb",
            },
            "test_library_path": "imported_test_library.ots.json",
            "transformations": [],
        }

        ots_file = models_dir / "schema1.ots.json"
        with open(ots_file, "w") as f:
            json.dump(imported_ots_module, f)

        project_config = {"name": "test_project"}
        imported_ots_modules = [(imported_ots_module, ots_file)]

        result = _merge_test_libraries(
            project_path, tests_folder, output_folder, project_config, imported_ots_modules
        )

        assert result is not None

        # Verify project version was used
        with open(result) as f:
            merged_lib = json.load(f)
            assert "test_conflict" in merged_lib["generic_tests"]
            # Project version should have "Project version" in description
            # (we can check the SQL content to verify it's the project version)
            test_sql = merged_lib["generic_tests"]["test_conflict"]["sql"]
            assert "SELECT 1" in test_sql  # Project version

    def test_merge_test_libraries_yaml_format(self, temp_dir):
        """Test merging test libraries with YAML export format."""
        project_path = temp_dir
        tests_folder = project_path / "tests"
        tests_folder.mkdir()
        output_folder = project_path / "output" / "ots_modules"
        output_folder.mkdir(parents=True)

        test_file = tests_folder / "test_minimum_rows.sql"
        test_file.write_text("""
SELECT 1 as violation FROM @table_name GROUP BY 1 HAVING COUNT(*) < @min_rows:10
""")

        project_config = {"name": "test_project"}
        imported_ots_modules = []

        result = _merge_test_libraries(
            project_path,
            tests_folder,
            output_folder,
            project_config,
            imported_ots_modules,
            format="yaml",
        )

        assert result is not None
        assert result.exists()
        assert result.suffixes == [".ots", ".yaml"]

        # Verify YAML is valid
        with open(result) as f:
            test_lib = yaml.safe_load(f)
            assert "generic_tests" in test_lib
            assert "test_minimum_rows" in test_lib["generic_tests"]  # Test name comes from filename

    def test_merge_test_libraries_no_tests(self, temp_dir):
        """Test merging when no tests exist."""
        project_path = temp_dir
        tests_folder = project_path / "tests"
        tests_folder.mkdir()
        output_folder = project_path / "output" / "ots_modules"
        output_folder.mkdir(parents=True)

        project_config = {"name": "test_project"}
        imported_ots_modules = []

        result = _merge_test_libraries(
            project_path, tests_folder, output_folder, project_config, imported_ots_modules
        )

        # Should return None when no tests found
        assert result is None
