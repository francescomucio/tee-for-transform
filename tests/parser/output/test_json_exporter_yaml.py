"""
Unit tests for JSONExporter YAML export functionality.
"""

import json
import tempfile
from pathlib import Path

import pytest
import yaml

from t4t.parser.output import JSONExporter
from t4t.typing import Function, Model


class TestJSONExporterYAML:
    """Test cases for YAML export in JSONExporter."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def sample_parsed_models(self) -> dict[str, Model]:
        """Create sample parsed models for testing."""
        return {
            "schema1.table1": {
                "code": {
                    "sql": {
                        "original_sql": "SELECT 1 as id, 'test' as name",
                        "operation_type": "select",
                    }
                },
                "model_metadata": {
                    "table_name": "schema1.table1",
                    "description": "Test table",
                    "metadata": {
                        "materialization": "table",
                    },
                },
                "sqlglot_hash": "abc123",
            },
        }

    @pytest.fixture
    def project_config(self):
        """Create sample project config."""
        return {
            "project_folder": "test_project",
            "connection": {
                "type": "duckdb",
                "path": ":memory:",
            },
        }

    def test_export_ots_modules_json_default(self, temp_dir, sample_parsed_models, project_config):
        """Test that JSON is the default format."""
        exporter = JSONExporter(temp_dir, project_config)

        results = exporter.export_ots_modules(sample_parsed_models)

        assert len(results) == 1
        output_file = results["test_project.schema1"]
        assert output_file.exists()
        assert output_file.suffixes == [".ots", ".json"]

        # Verify JSON content
        with open(output_file) as f:
            module_data = json.load(f)
            assert module_data["ots_version"] == "0.2.2"
            assert module_data["module_name"] == "test_project.schema1"

    def test_export_ots_modules_yaml(self, temp_dir, sample_parsed_models, project_config):
        """Test YAML export format."""
        exporter = JSONExporter(temp_dir, project_config)

        results = exporter.export_ots_modules(sample_parsed_models, format="yaml")

        assert len(results) == 1
        output_file = results["test_project.schema1"]
        assert output_file.exists()
        assert output_file.suffixes == [".ots", ".yaml"]

        # Verify YAML content
        with open(output_file) as f:
            module_data = yaml.safe_load(f)
            assert module_data["ots_version"] == "0.2.2"
            assert module_data["module_name"] == "test_project.schema1"
            assert len(module_data["transformations"]) == 1

    def test_export_ots_modules_both_formats(self, temp_dir, sample_parsed_models, project_config):
        """Test exporting in both JSON and YAML formats."""
        exporter = JSONExporter(temp_dir, project_config)

        # Export as JSON
        json_results = exporter.export_ots_modules(sample_parsed_models, format="json")
        json_file = json_results["test_project.schema1"]

        # Export as YAML (to different directory to avoid overwrite)
        yaml_dir = temp_dir / "yaml_output"
        yaml_exporter = JSONExporter(yaml_dir, project_config)
        yaml_results = yaml_exporter.export_ots_modules(sample_parsed_models, format="yaml")
        yaml_file = yaml_results["test_project.schema1"]

        # Both should exist
        assert json_file.exists()
        assert yaml_file.exists()

        # Both should have same content structure
        with open(json_file) as f:
            json_data = json.load(f)
        with open(yaml_file) as f:
            yaml_data = yaml.safe_load(f)

        assert json_data["ots_version"] == yaml_data["ots_version"]
        assert json_data["module_name"] == yaml_data["module_name"]
        assert len(json_data["transformations"]) == len(yaml_data["transformations"])

    def test_export_ots_modules_with_functions(
        self, temp_dir, sample_parsed_models, project_config
    ):
        """Test exporting OTS modules with functions."""
        sample_function: Function = {
            "function_metadata": {
                "function_name": "calculate_percentage",
                "function_type": "scalar",
                "language": "sql",
                "schema": "schema1",
                "file_path": "functions/schema1/calculate_percentage.sql",
            },
            "code": {
                "sql": {
                    "original_sql": "CREATE FUNCTION calculate_percentage(n FLOAT, d FLOAT) RETURNS FLOAT AS $$ SELECT n/d*100 $$",
                }
            },
        }
        parsed_functions = {"schema1.calculate_percentage": sample_function}

        exporter = JSONExporter(temp_dir, project_config)
        results = exporter.export_ots_modules(
            sample_parsed_models, parsed_functions=parsed_functions
        )

        assert len(results) == 1
        output_file = results["test_project.schema1"]
        assert output_file.exists()

        # Verify module contains functions
        with open(output_file) as f:
            module_data = json.load(f)
            assert module_data["ots_version"] == "0.2.2"
            assert "functions" in module_data
            assert len(module_data["functions"]) == 1
            assert module_data["functions"][0]["function_id"] == "schema1.calculate_percentage"

    def test_export_ots_modules_without_functions(
        self, temp_dir, sample_parsed_models, project_config
    ):
        """Test that OTS version is 0.1.0 when no functions are exported."""
        exporter = JSONExporter(temp_dir, project_config)
        results = exporter.export_ots_modules(sample_parsed_models)

        assert len(results) == 1
        output_file = results["test_project.schema1"]

        with open(output_file) as f:
            module_data = json.load(f)
            assert module_data["ots_version"] == "0.2.2"
            assert "functions" not in module_data


class TestTestLibraryExporterYAML:
    """Test cases for YAML export in TestLibraryExporter."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_export_test_library_yaml(self, temp_dir):
        """Test exporting test library in YAML format."""
        from t4t.parser.output import TestLibraryExporter

        # Create test file
        tests_dir = temp_dir / "tests"
        tests_dir.mkdir()
        test_file = tests_dir / "test_minimum_rows.sql"
        test_file.write_text("""
SELECT 1 as violation
FROM @table_name
GROUP BY 1
HAVING COUNT(*) < @min_rows:10
""")

        output_folder = temp_dir / "output"
        output_folder.mkdir()

        exporter = TestLibraryExporter(temp_dir, "test_project")
        result = exporter.export_test_library(output_folder, format="yaml")

        assert result is not None
        assert result.exists()
        assert result.suffixes == [".ots", ".yaml"]

        # Verify YAML content
        with open(result) as f:
            test_lib = yaml.safe_load(f)
            assert "test_library_version" in test_lib
            assert "generic_tests" in test_lib
            assert "test_minimum_rows" in test_lib["generic_tests"]
