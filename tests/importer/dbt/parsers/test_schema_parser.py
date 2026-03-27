"""
Tests for the schema parser.
"""

import tempfile
from pathlib import Path

import yaml

from tee.importer.dbt.parsers import SchemaParser


class TestSchemaParser:
    """Tests for schema parser."""

    def test_parse_schema_file_simple(self):
        """Test parsing a simple schema.yml file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            schema_file = Path(tmpdir) / "schema.yml"
            schema_content = {
                "models": [
                    {
                        "name": "customers",
                        "description": "Customer table",
                        "columns": [
                            {"name": "id", "data_type": "integer"},
                            {"name": "name", "data_type": "varchar"},
                        ],
                    }
                ]
            }
            with schema_file.open("w", encoding="utf-8") as f:
                yaml.dump(schema_content, f)

            parser = SchemaParser()
            models = parser.parse_schema_file(schema_file)

            assert "customers" in models
            assert models["customers"]["name"] == "customers"
            assert models["customers"]["description"] == "Customer table"
            assert len(models["customers"]["columns"]) == 2

    def test_parse_schema_file_multiple_models(self):
        """Test parsing schema file with multiple models."""
        with tempfile.TemporaryDirectory() as tmpdir:
            schema_file = Path(tmpdir) / "schema.yml"
            schema_content = {
                "models": [
                    {"name": "customers", "description": "Customers"},
                    {"name": "orders", "description": "Orders"},
                    {"name": "products", "description": "Products"},
                ]
            }
            with schema_file.open("w", encoding="utf-8") as f:
                yaml.dump(schema_content, f)

            parser = SchemaParser()
            models = parser.parse_schema_file(schema_file)

            assert len(models) == 3
            assert "customers" in models
            assert "orders" in models
            assert "products" in models

    def test_parse_schema_file_with_tests(self):
        """Test parsing schema file with tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            schema_file = Path(tmpdir) / "schema.yml"
            schema_content = {
                "models": [
                    {
                        "name": "customers",
                        "columns": [
                            {
                                "name": "id",
                                "data_type": "integer",
                                "tests": ["not_null", "unique"],
                            }
                        ],
                        "tests": ["accepted_values"],
                    }
                ]
            }
            with schema_file.open("w", encoding="utf-8") as f:
                yaml.dump(schema_content, f)

            parser = SchemaParser()
            models = parser.parse_schema_file(schema_file)

            assert "customers" in models
            assert "tests" in models["customers"]
            assert "tests" in models["customers"]["columns"][0]

    def test_parse_schema_file_invalid_yaml(self):
        """Test parsing invalid YAML file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            schema_file = Path(tmpdir) / "schema.yml"
            schema_file.write_text("invalid: yaml: content: [")

            parser = SchemaParser()
            models = parser.parse_schema_file(schema_file)

            # Should return empty dict on error
            assert models == {}

    def test_parse_schema_file_not_dict(self):
        """Test parsing YAML that is not a dictionary."""
        with tempfile.TemporaryDirectory() as tmpdir:
            schema_file = Path(tmpdir) / "schema.yml"
            schema_file.write_text("- item1\n- item2")

            parser = SchemaParser()
            models = parser.parse_schema_file(schema_file)

            # Should return empty dict
            assert models == {}

    def test_parse_schema_file_no_models_key(self):
        """Test parsing schema file without models key."""
        with tempfile.TemporaryDirectory() as tmpdir:
            schema_file = Path(tmpdir) / "schema.yml"
            schema_content = {"sources": [{"name": "raw"}]}
            with schema_file.open("w", encoding="utf-8") as f:
                yaml.dump(schema_content, f)

            parser = SchemaParser()
            models = parser.parse_schema_file(schema_file)

            # Should return empty dict
            assert models == {}

    def test_parse_schema_file_invalid_model_format(self):
        """Test parsing schema file with invalid model format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            schema_file = Path(tmpdir) / "schema.yml"
            schema_content = {
                "models": [
                    "not a dict",
                    {"name": "valid_model"},
                    {"no_name": "invalid"},
                ]
            }
            with schema_file.open("w", encoding="utf-8") as f:
                yaml.dump(schema_content, f)

            parser = SchemaParser()
            models = parser.parse_schema_file(schema_file)

            # Should only include valid model
            assert len(models) == 1
            assert "valid_model" in models

    def test_parse_all_schema_files(self):
        """Test parsing multiple schema files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            schema_file1 = Path(tmpdir) / "schema1.yml"
            schema_file2 = Path(tmpdir) / "schema2.yml"

            schema_content1 = {
                "models": [
                    {"name": "customers", "description": "Customers"},
                    {"name": "orders", "description": "Orders"},
                ]
            }
            schema_content2 = {
                "models": [
                    {"name": "products", "description": "Products"},
                ]
            }

            with schema_file1.open("w", encoding="utf-8") as f:
                yaml.dump(schema_content1, f)
            with schema_file2.open("w", encoding="utf-8") as f:
                yaml.dump(schema_content2, f)

            parser = SchemaParser()
            schema_files = {
                "schema1.yml": schema_file1,
                "schema2.yml": schema_file2,
            }
            models = parser.parse_all_schema_files(schema_files)

            assert len(models) == 3
            assert "customers" in models
            assert "orders" in models
            assert "products" in models

    def test_parse_all_schema_files_override(self):
        """Test that later schema files override earlier ones."""
        with tempfile.TemporaryDirectory() as tmpdir:
            schema_file1 = Path(tmpdir) / "schema1.yml"
            schema_file2 = Path(tmpdir) / "schema2.yml"

            schema_content1 = {
                "models": [
                    {"name": "customers", "description": "Old description"},
                ]
            }
            schema_content2 = {
                "models": [
                    {"name": "customers", "description": "New description"},
                ]
            }

            with schema_file1.open("w", encoding="utf-8") as f:
                yaml.dump(schema_content1, f)
            with schema_file2.open("w", encoding="utf-8") as f:
                yaml.dump(schema_content2, f)

            parser = SchemaParser()
            schema_files = {
                "schema1.yml": schema_file1,
                "schema2.yml": schema_file2,
            }
            models = parser.parse_all_schema_files(schema_files)

            assert models["customers"]["description"] == "New description"

    def test_parse_schema_file_verbose(self):
        """Test parsing with verbose mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            schema_file = Path(tmpdir) / "schema.yml"
            schema_content = {
                "models": [
                    {"name": "customers"},
                ]
            }
            with schema_file.open("w", encoding="utf-8") as f:
                yaml.dump(schema_content, f)

            parser = SchemaParser(verbose=True)
            models = parser.parse_schema_file(schema_file)

            assert "customers" in models
