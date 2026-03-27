"""
Tests for tag extraction from multiple sources.
"""

from pathlib import Path

from tee.importer.dbt.converters import MetadataConverter
from tee.importer.dbt.parsers import ConfigExtractor
from tee.importer.dbt.resolvers import SchemaResolver


class TestTagsExtraction:
    """Tests for additive tag extraction."""

    def test_tags_from_model_config(self):
        """Test extracting tags from model file config block."""
        sql = """{{ config(tags=['model_tag1', 'model_tag2']) }}

SELECT * FROM customers
"""
        extractor = ConfigExtractor()
        config = extractor.extract_config(sql)

        assert "tags" in config
        assert config["tags"] == ["model_tag1", "model_tag2"]

    def test_tags_from_schema_yml(self):
        """Test extracting tags from schema.yml."""
        schema_metadata = {
            "name": "customers",
            "tags": ["schema_tag1", "schema_tag2"],
            "config": {"tags": ["config_tag1"]},
        }

        converter = MetadataConverter()
        tags = converter._collect_tags_additively(schema_metadata, None, None)

        # Should combine tags from root and config block
        assert "schema_tag1" in tags
        assert "schema_tag2" in tags
        assert "config_tag1" in tags

    def test_tags_additive_all_sources(self):
        """Test that tags are combined from all sources."""
        schema_metadata = {
            "name": "customers",
            "tags": ["schema_tag"],
        }
        model_config = {"tags": ["model_tag"]}
        project_tags = ["project_tag"]

        converter = MetadataConverter()
        tags = converter._collect_tags_additively(schema_metadata, model_config, project_tags)

        # Should have all tags
        assert len(tags) == 3
        assert "project_tag" in tags
        assert "schema_tag" in tags
        assert "model_tag" in tags

    def test_tags_from_dbt_project_yml(self):
        """Test extracting tags from dbt_project.yml."""
        dbt_config = {
            "name": "test_project",
            "models": {
                "test_project": {
                    "staging": {"tags": ["folder_tag"], "customers": {"tags": ["model_tag"]}}
                }
            },
        }
        dbt_project = {"name": "test_project", "raw_config": dbt_config}
        resolver = SchemaResolver(dbt_project)

        # Test folder-level tags
        model_path = Path("/path/to/models/staging/orders.sql")
        tags = resolver.extract_tags_from_project_config("orders", model_path)
        assert "folder_tag" in tags

        # Test model-specific tags
        model_path = Path("/path/to/models/staging/customers.sql")
        tags = resolver.extract_tags_from_project_config("customers", model_path)
        assert "model_tag" in tags
        # Model-specific tags should override folder tags
        assert "folder_tag" not in tags or "model_tag" in tags

    def test_tags_remove_duplicates(self):
        """Test that duplicate tags are removed."""
        schema_metadata = {"tags": ["tag1", "tag2"]}
        model_config = {
            "tags": ["tag2", "tag3"]  # tag2 is duplicate
        }

        converter = MetadataConverter()
        tags = converter._collect_tags_additively(schema_metadata, model_config, None)

        # Should have 3 unique tags
        assert len(tags) == 3
        assert tags.count("tag2") == 1  # No duplicates
        assert set(tags) == {"tag1", "tag2", "tag3"}  # All unique

    def test_tags_remove_duplicates_all_sources(self):
        """Test that duplicate tags are removed across all sources."""
        schema_metadata = {
            "tags": ["tag1", "tag2"],
            "config": {
                "tags": ["tag2", "tag3"]  # tag2 duplicate from root
            },
        }
        model_config = {
            "tags": ["tag3", "tag4"]  # tag3 duplicate from schema config
        }
        project_tags = ["tag1", "tag4"]  # tag1 duplicate from schema, tag4 from model

        converter = MetadataConverter()
        tags = converter._collect_tags_additively(schema_metadata, model_config, project_tags)

        # Should have 4 unique tags: tag1, tag2, tag3, tag4
        # Order: project (tag1, tag4) -> schema root (tag1, tag2) -> schema config (tag2, tag3) -> model (tag3, tag4)
        # After dedup: tag1, tag4, tag2, tag3
        assert len(tags) == 4
        assert set(tags) == {"tag1", "tag2", "tag3", "tag4"}
        # First occurrence should be preserved
        assert tags[0] == "tag1"  # From project_tags
        assert tags.index("tag2") < tags.index(
            "tag3"
        )  # tag2 appears before tag3 (from schema root before schema config)

    def test_tags_preserve_order(self):
        """Test that tag order is preserved (first occurrence wins)."""
        schema_metadata = {"tags": ["tag1", "tag2"]}
        model_config = {
            "tags": ["tag2", "tag3"]  # tag2 appears again
        }

        converter = MetadataConverter()
        tags = converter._collect_tags_additively(schema_metadata, model_config, None)

        # Order should be: schema tags first, then model tags (duplicates removed)
        assert tags == ["tag1", "tag2", "tag3"]
