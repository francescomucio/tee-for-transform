"""
Test cases for OTS transformer tag extraction and merging functionality.
"""

from t4t.parser.output.ots.taggers import TagManager
from t4t.parser.output.ots.transformer import OTSTransformer
from t4t.typing import Model


class TestOTSTagExtraction:
    """Test tag extraction from project config and model metadata."""

    def test_extract_module_tags_from_module_section(self):
        """Test extraction of module tags from [module] section in project config."""
        project_config = {
            "project_folder": "test_project",
            "connection": {"type": "duckdb", "path": ":memory:"},
            "module": {"tags": ["analytics", "production", "fct"]},
        }

        tag_manager = TagManager(project_config)
        tags = tag_manager.merge_tags([])
        assert tags == ["analytics", "production", "fct"]

    def test_extract_module_tags_from_root_level(self):
        """Test extraction of module tags from root level in project config."""
        project_config = {
            "project_folder": "test_project",
            "connection": {"type": "duckdb", "path": ":memory:"},
            "tags": ["analytics", "production"],
        }

        tag_manager = TagManager(project_config)
        tags = tag_manager.merge_tags([])
        assert tags == ["analytics", "production"]

    def test_merge_module_and_transformation_tags(self):
        """Test merging module tags with transformation-specific tags."""
        project_config = {
            "project_folder": "test_project",
            "connection": {"type": "duckdb", "path": ":memory:"},
            "module": {"tags": ["analytics", "production"]},
        }

        tag_manager = TagManager(project_config)
        transformation_tags = ["fct", "daily"]
        tags = tag_manager.merge_tags(transformation_tags)
        # Should merge and preserve order: module tags first, then transformation tags
        assert tags == ["analytics", "production", "fct", "daily"]

    def test_deduplicate_tags(self):
        """Test that duplicate tags are removed while preserving order."""
        project_config = {
            "project_folder": "test_project",
            "connection": {"type": "duckdb", "path": ":memory:"},
            "module": {"tags": ["analytics", "production"]},
        }

        tag_manager = TagManager(project_config)
        transformation_tags = ["analytics", "fct"]  # "analytics" is duplicate
        tags = tag_manager.merge_tags(transformation_tags)
        # Should deduplicate (case-insensitive) and preserve order
        assert tags == ["analytics", "production", "fct"]

    def test_case_insensitive_deduplication(self):
        """Test that tag deduplication is case-insensitive."""
        project_config = {
            "project_folder": "test_project",
            "connection": {"type": "duckdb", "path": ":memory:"},
            "module": {"tags": ["Analytics", "PRODUCTION"]},
        }

        tag_manager = TagManager(project_config)
        transformation_tags = ["analytics", "production"]  # Lowercase duplicates
        tags = tag_manager.merge_tags(transformation_tags)
        # Should deduplicate case-insensitively, keeping first occurrence
        assert len(tags) == 2
        assert "Analytics" in tags or "analytics" in tags
        assert "PRODUCTION" in tags or "production" in tags

    def test_no_module_tags_returns_transformation_tags(self):
        """Test that when no module tags exist, only transformation tags are returned."""
        project_config = {
            "project_folder": "test_project",
            "connection": {"type": "duckdb", "path": ":memory:"},
        }

        tag_manager = TagManager(project_config)
        transformation_tags = ["fct", "daily"]
        tags = tag_manager.merge_tags(transformation_tags)
        assert tags == ["fct", "daily"]

    def test_no_tags_returns_empty_list(self):
        """Test that when no tags exist, empty list is returned."""
        project_config = {
            "project_folder": "test_project",
            "connection": {"type": "duckdb", "path": ":memory:"},
        }

        tag_manager = TagManager(project_config)
        tags = tag_manager.merge_tags([])
        assert tags == []

    def test_module_tags_in_ots_module(self):
        """Test that module-level tags are added to OTS module structure."""
        project_config = {
            "project_folder": "test_project",
            "connection": {"type": "duckdb", "path": ":memory:"},
            "module": {"tags": ["analytics", "production"]},
        }

        transformer = OTSTransformer(project_config)
        parsed_models: dict[str, Model] = {
            "schema.table1": {
                "model_metadata": {
                    "metadata": {},
                    "file_path": "models/table1.sql",
                },
                "code": {
                    "sql": {
                        "original_sql": "SELECT 1 as id",
                        "resolved_sql": "SELECT 1 as id",
                        "source_tables": [],
                    }
                },
            }
        }

        modules = transformer.transform_to_ots_modules(parsed_models)
        assert len(modules) == 1

        module = modules["test_project.schema"]
        assert "tags" in module
        assert module["tags"] == ["analytics", "production"]

    def test_transformation_tags_in_ots_transformation(self):
        """Test that transformation tags are added to OTS transformation metadata."""
        project_config = {
            "project_folder": "test_project",
            "connection": {"type": "duckdb", "path": ":memory:"},
        }

        transformer = OTSTransformer(project_config)
        parsed_models: dict[str, Model] = {
            "schema.table1": {
                "model_metadata": {
                    "metadata": {"tags": ["fct", "daily"]},
                    "file_path": "models/table1.sql",
                },
                "code": {
                    "sql": {
                        "original_sql": "SELECT 1 as id",
                        "resolved_sql": "SELECT 1 as id",
                        "source_tables": [],
                    }
                },
            }
        }

        modules = transformer.transform_to_ots_modules(parsed_models)
        assert len(modules) == 1

        module = modules["test_project.schema"]
        assert len(module["transformations"]) == 1

        transformation = module["transformations"][0]
        assert "metadata" in transformation
        assert "tags" in transformation["metadata"]
        assert transformation["metadata"]["tags"] == ["fct", "daily"]

    def test_merged_tags_in_transformation_metadata(self):
        """Test that merged tags (module + transformation) are in transformation metadata."""
        project_config = {
            "project_folder": "test_project",
            "connection": {"type": "duckdb", "path": ":memory:"},
            "module": {"tags": ["analytics", "production"]},
        }

        transformer = OTSTransformer(project_config)
        parsed_models: dict[str, Model] = {
            "schema.table1": {
                "model_metadata": {
                    "metadata": {"tags": ["fct", "daily"]},
                    "file_path": "models/table1.sql",
                },
                "code": {
                    "sql": {
                        "original_sql": "SELECT 1 as id",
                        "resolved_sql": "SELECT 1 as id",
                        "source_tables": [],
                    }
                },
            }
        }

        modules = transformer.transform_to_ots_modules(parsed_models)
        transformation = modules["test_project.schema"]["transformations"][0]

        # Transformation should have merged tags
        assert "metadata" in transformation
        assert "tags" in transformation["metadata"]
        tags = transformation["metadata"]["tags"]
        assert "analytics" in tags
        assert "production" in tags
        assert "fct" in tags
        assert "daily" in tags

    def test_handle_invalid_tag_types(self):
        """Test handling of invalid tag types (non-list values)."""
        project_config = {
            "project_folder": "test_project",
            "connection": {"type": "duckdb", "path": ":memory:"},
            "module": {"tags": "not-a-list"},  # Invalid: should be a list
        }

        tag_manager = TagManager(project_config)
        transformation_tags = ["valid", "tags"]
        tags = tag_manager.merge_tags(transformation_tags)
        # Should handle gracefully and only use valid tags
        assert tags == ["valid", "tags"]

    def test_handle_empty_string_tags(self):
        """Test handling of empty string tags."""
        project_config = {
            "project_folder": "test_project",
            "connection": {"type": "duckdb", "path": ":memory:"},
            "module": {"tags": ["valid", "", "  ", None, "also-valid"]},
        }

        tag_manager = TagManager(project_config)
        tags = tag_manager.merge_tags([])
        # Should filter out empty/None values
        assert "valid" in tags
        assert "also-valid" in tags
        assert "" not in tags
        assert None not in tags

    def test_extract_object_tags_from_metadata(self):
        """Test extraction of object_tags (key-value pairs) from model metadata."""
        project_config = {
            "project_folder": "test_project",
            "connection": {"type": "duckdb", "path": ":memory:"},
        }

        tag_manager = TagManager(project_config)
        metadata = {
            "object_tags": {
                "sensitivity_tag": "pii",
                "classification": "public",
                "data_owner": "analytics-team",
            }
        }
        object_tags = tag_manager.extract_object_tags(metadata)
        assert isinstance(object_tags, dict)
        assert object_tags["sensitivity_tag"] == "pii"
        assert object_tags["classification"] == "public"
        assert object_tags["data_owner"] == "analytics-team"

    def test_extract_object_tags_handles_non_dict(self):
        """Test that non-dict object_tags are handled gracefully."""
        project_config = {
            "project_folder": "test_project",
            "connection": {"type": "duckdb", "path": ":memory:"},
        }

        tag_manager = TagManager(project_config)
        metadata = {
            "object_tags": ["not", "a", "dict"]  # Invalid format
        }
        object_tags = tag_manager.extract_object_tags(metadata)
        assert object_tags == {}

    def test_extract_object_tags_converts_values_to_strings(self):
        """Test that object_tag values are converted to strings."""
        project_config = {
            "project_folder": "test_project",
            "connection": {"type": "duckdb", "path": ":memory:"},
        }

        tag_manager = TagManager(project_config)
        metadata = {
            "object_tags": {"numeric_value": 123, "boolean_value": True, "string_value": "text"}
        }
        object_tags = tag_manager.extract_object_tags(metadata)
        assert object_tags["numeric_value"] == "123"
        assert object_tags["boolean_value"] == "True"
        assert object_tags["string_value"] == "text"

    def test_object_tags_in_ots_transformation(self):
        """Test that object_tags are added to OTS transformation metadata."""
        project_config = {
            "project_folder": "test_project",
            "connection": {"type": "duckdb", "path": ":memory:"},
        }

        transformer = OTSTransformer(project_config)
        parsed_models: dict[str, Model] = {
            "schema.table1": {
                "model_metadata": {
                    "metadata": {
                        "object_tags": {"sensitivity_tag": "pii", "classification": "public"}
                    },
                    "file_path": "models/table1.sql",
                },
                "code": {
                    "sql": {
                        "original_sql": "SELECT 1 as id",
                        "resolved_sql": "SELECT 1 as id",
                        "source_tables": [],
                    }
                },
            }
        }

        modules = transformer.transform_to_ots_modules(parsed_models)
        transformation = modules["test_project.schema"]["transformations"][0]

        assert "metadata" in transformation
        assert "object_tags" in transformation["metadata"]
        assert transformation["metadata"]["object_tags"]["sensitivity_tag"] == "pii"
        assert transformation["metadata"]["object_tags"]["classification"] == "public"

    def test_both_tags_and_object_tags_in_transformation(self):
        """Test that both tags and object_tags can coexist in a transformation."""
        project_config = {
            "project_folder": "test_project",
            "connection": {"type": "duckdb", "path": ":memory:"},
        }

        transformer = OTSTransformer(project_config)
        parsed_models: dict[str, Model] = {
            "schema.table1": {
                "model_metadata": {
                    "metadata": {
                        "tags": ["analytics", "production"],  # dbt-style
                        "object_tags": {  # database-style
                            "sensitivity_tag": "pii",
                            "classification": "public",
                        },
                    },
                    "file_path": "models/table1.sql",
                },
                "code": {
                    "sql": {
                        "original_sql": "SELECT 1 as id",
                        "resolved_sql": "SELECT 1 as id",
                        "source_tables": [],
                    }
                },
            }
        }

        modules = transformer.transform_to_ots_modules(parsed_models)
        transformation = modules["test_project.schema"]["transformations"][0]

        # Should have both
        assert "metadata" in transformation
        assert "tags" in transformation["metadata"]
        assert "object_tags" in transformation["metadata"]
        assert transformation["metadata"]["tags"] == ["analytics", "production"]
        assert transformation["metadata"]["object_tags"]["sensitivity_tag"] == "pii"
