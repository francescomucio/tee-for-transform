"""
Tests for OTS to Model converter.
"""

from t4t.parser.input import OTSConverter
from t4t.typing.metadata import OTSModule


class TestOTSConverter:
    """Tests for OTSConverter."""

    def test_convert_simple_module(self):
        """Test converting a simple OTS module."""
        converter = OTSConverter()

        module: OTSModule = {
            "ots_version": "0.1.0",
            "module_name": "test.module",
            "target": {
                "database": "test_db",
                "schema": "test_schema",
            },
            "transformations": [
                {
                    "transformation_id": "test_schema.test_table",
                    "description": "Test table",
                    "code": {
                        "sql": {
                            "original_sql": "SELECT 1 as col1, 'test' as col2",
                            "resolved_sql": "SELECT 1 as col1, 'test' as col2",
                            "source_tables": [],
                        }
                    },
                    "schema": {
                        "columns": [
                            {"name": "col1", "datatype": "number"},
                            {"name": "col2", "datatype": "string"},
                        ]
                    },
                    "materialization": {"type": "table"},
                    "metadata": {"file_path": "test.sql"},
                }
            ],
        }

        parsed_models, parsed_functions = converter.convert_module(module)
        assert len(parsed_models) == 1
        assert len(parsed_functions) == 0
        assert "test_schema.test_table" in parsed_models

        parsed_model = parsed_models["test_schema.test_table"]
        assert "code" in parsed_model
        assert "model_metadata" in parsed_model
        assert parsed_model["code"]["sql"]["original_sql"] == "SELECT 1 as col1, 'test' as col2"

    def test_convert_module_with_tests(self):
        """Test converting a module with tests."""
        converter = OTSConverter()

        module: OTSModule = {
            "ots_version": "0.1.0",
            "module_name": "test.module",
            "target": {
                "database": "test_db",
                "schema": "test_schema",
            },
            "transformations": [
                {
                    "transformation_id": "test_schema.test_table",
                    "code": {
                        "sql": {
                            "original_sql": "SELECT 1 as id",
                            "resolved_sql": "SELECT 1 as id",
                            "source_tables": [],
                        }
                    },
                    "schema": {
                        "columns": [
                            {"name": "id", "datatype": "number"},
                        ]
                    },
                    "materialization": {"type": "table"},
                    "tests": {
                        "columns": {
                            "id": ["not_null", "unique"],
                        },
                        "table": ["row_count_gt_0"],
                    },
                    "metadata": {},
                }
            ],
        }

        parsed_models, parsed_functions = converter.convert_module(module)
        parsed_model = parsed_models["test_schema.test_table"]

        # Check that tests are attached
        metadata = parsed_model["model_metadata"]["metadata"]
        assert "tests" in metadata
        assert "row_count_gt_0" in metadata["tests"]

        # Check column tests
        schema = metadata["schema"]
        id_col = next(col for col in schema if col["name"] == "id")
        assert "tests" in id_col
        assert "not_null" in id_col["tests"]
        assert "unique" in id_col["tests"]

    def test_convert_module_with_incremental(self):
        """Test converting a module with incremental materialization."""
        converter = OTSConverter()

        module: OTSModule = {
            "ots_version": "0.1.0",
            "module_name": "test.module",
            "target": {
                "database": "test_db",
                "schema": "test_schema",
            },
            "transformations": [
                {
                    "transformation_id": "test_schema.test_table",
                    "code": {
                        "sql": {
                            "original_sql": "SELECT 1 as id",
                            "resolved_sql": "SELECT 1 as id",
                            "source_tables": [],
                        }
                    },
                    "materialization": {
                        "type": "incremental",
                        "incremental_details": {
                            "strategy": "append",
                            "filter_condition": "created_at >= '2024-01-01'",
                        },
                    },
                    "metadata": {},
                }
            ],
        }

        parsed_models, parsed_functions = converter.convert_module(module)
        parsed_model = parsed_models["test_schema.test_table"]

        metadata = parsed_model["model_metadata"]["metadata"]
        assert metadata["materialization"] == "incremental"
        assert "incremental" in metadata
        assert metadata["incremental"]["strategy"] == "append"

    def test_convert_module_with_tags(self):
        """Test converting a module with tags."""
        converter = OTSConverter()

        module: OTSModule = {
            "ots_version": "0.1.0",
            "module_name": "test.module",
            "tags": ["module_tag1", "module_tag2"],
            "target": {
                "database": "test_db",
                "schema": "test_schema",
            },
            "transformations": [
                {
                    "transformation_id": "test_schema.test_table",
                    "code": {
                        "sql": {
                            "original_sql": "SELECT 1",
                            "resolved_sql": "SELECT 1",
                            "source_tables": [],
                        }
                    },
                    "materialization": {"type": "table"},
                    "metadata": {
                        "tags": ["transformation_tag1"],
                    },
                }
            ],
        }

        parsed_models, parsed_functions = converter.convert_module(module)
        parsed_model = parsed_models["test_schema.test_table"]

        metadata = parsed_model["model_metadata"]["metadata"]
        assert "tags" in metadata
        # Should merge module and transformation tags
        tags = metadata["tags"]
        assert "module_tag1" in tags
        assert "module_tag2" in tags
        assert "transformation_tag1" in tags
