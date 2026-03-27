"""
Test cases for tag extraction in execution engine.
"""

from tee.engine.execution_engine import ExecutionEngine
from tee.engine.metadata import MetadataExtractor


class TestTagExtraction:
    """Test tag extraction from model metadata in execution engine."""

    def test_extract_tags_from_nested_metadata(self, temp_project_dir):
        """Test extraction of tags from nested metadata structure."""
        ExecutionEngine(
            config={"type": "duckdb", "path": ":memory:"},
            project_folder=str(temp_project_dir),
        )

        model_data = {
            "model_metadata": {
                "metadata": {
                    "tags": ["fct", "daily"],
                    "schema": [{"name": "id", "datatype": "INTEGER"}],
                }
            },
            "code": {
                "sql": {
                    "original_sql": "SELECT 1 as id",
                    "resolved_sql": "SELECT 1 as id",
                    "source_tables": [],
                }
            },
        }

        metadata_extractor = MetadataExtractor()
        metadata = metadata_extractor.extract_model_metadata(model_data)
        assert metadata is not None
        assert "tags" in metadata
        assert metadata["tags"] == ["fct", "daily"]

    def test_extract_tags_from_deeply_nested_metadata(self, temp_project_dir):
        """Test extraction of tags from deeply nested metadata structure."""
        ExecutionEngine(
            config={"type": "duckdb", "path": ":memory:"},
            project_folder=str(temp_project_dir),
        )

        model_data = {
            "model_metadata": {
                "metadata": {
                    "metadata": {
                        "tags": ["analytics", "production"],
                        "schema": [{"name": "id", "datatype": "INTEGER"}],
                    }
                }
            },
            "code": {
                "sql": {
                    "original_sql": "SELECT 1 as id",
                    "resolved_sql": "SELECT 1 as id",
                    "source_tables": [],
                }
            },
        }

        metadata_extractor = MetadataExtractor()
        metadata = metadata_extractor.extract_model_metadata(model_data)
        assert metadata is not None
        assert "tags" in metadata
        assert metadata["tags"] == ["analytics", "production"]

    def test_extract_tags_from_file_metadata(self, temp_project_dir):
        """Test extraction of tags from file-level metadata."""
        ExecutionEngine(
            config={"type": "duckdb", "path": ":memory:"},
            project_folder=str(temp_project_dir),
        )

        model_data = {
            "model_metadata": {
                "description": "Test model",
            },
            "metadata": {
                "tags": ["staging", "test"],
                "schema": [{"name": "id", "datatype": "INTEGER"}],
            },
            "code": {
                "sql": {
                    "original_sql": "SELECT 1 as id",
                    "resolved_sql": "SELECT 1 as id",
                    "source_tables": [],
                }
            },
        }

        metadata_extractor = MetadataExtractor()
        metadata = metadata_extractor.extract_model_metadata(model_data)
        assert metadata is not None
        assert "tags" in metadata
        assert metadata["tags"] == ["staging", "test"]

    def test_no_tags_returns_metadata_without_tags(self, temp_project_dir):
        """Test that metadata without tags is still returned."""
        ExecutionEngine(
            config={"type": "duckdb", "path": ":memory:"},
            project_folder=str(temp_project_dir),
        )

        model_data = {
            "model_metadata": {
                "metadata": {
                    "schema": [{"name": "id", "datatype": "INTEGER"}],
                }
            },
            "code": {
                "sql": {
                    "original_sql": "SELECT 1 as id",
                    "resolved_sql": "SELECT 1 as id",
                    "source_tables": [],
                }
            },
        }

        metadata_extractor = MetadataExtractor()
        metadata = metadata_extractor.extract_model_metadata(model_data)
        assert metadata is not None
        assert "tags" not in metadata or metadata.get("tags") == []

    def test_extract_tags_to_metadata_helper(self, temp_project_dir):
        """Test the _extract_tags_to_metadata helper method."""
        ExecutionEngine(
            config={"type": "duckdb", "path": ":memory:"},
            project_folder=str(temp_project_dir),
        )

        metadata = {}
        model_metadata = {"metadata": {"tags": ["test", "tags"]}}

        metadata_extractor = MetadataExtractor()
        metadata_extractor._extract_tags_to_metadata(metadata, model_metadata)
        assert "tags" in metadata
        assert metadata["tags"] == ["test", "tags"]

    def test_extract_tags_preserves_existing_tags(self, temp_project_dir):
        """Test that existing tags in metadata are preserved."""
        ExecutionEngine(
            config={"type": "duckdb", "path": ":memory:"},
            project_folder=str(temp_project_dir),
        )

        metadata = {"tags": ["existing"]}
        model_metadata = {"metadata": {"tags": ["new", "tags"]}}

        metadata_extractor = MetadataExtractor()
        metadata_extractor._extract_tags_to_metadata(metadata, model_metadata)
        # Should preserve existing tags (not overwrite)
        assert metadata["tags"] == ["existing"]

    def test_tags_in_incremental_metadata(self, temp_project_dir):
        """Test that tags are extracted from incremental materialization metadata."""
        ExecutionEngine(
            config={"type": "duckdb", "path": ":memory:"},
            project_folder=str(temp_project_dir),
        )

        model_data = {
            "model_metadata": {
                "metadata": {
                    "materialization": "incremental",
                    "tags": ["incremental", "daily"],
                    "incremental": {
                        "strategy": "append",
                        "append": {"filter_column": "created_at"},
                    },
                }
            },
            "code": {
                "sql": {
                    "original_sql": "SELECT 1 as id",
                    "resolved_sql": "SELECT 1 as id",
                    "source_tables": [],
                }
            },
        }

        metadata_extractor = MetadataExtractor()
        metadata = metadata_extractor.extract_model_metadata(model_data)
        assert metadata is not None
        assert "tags" in metadata
        assert metadata["tags"] == ["incremental", "daily"]
        assert metadata["materialization"] == "incremental"

    def test_extract_object_tags_from_metadata(self, temp_project_dir):
        """Test extraction of object_tags (key-value pairs) from metadata."""
        ExecutionEngine(
            config={"type": "duckdb", "path": ":memory:"},
            project_folder=str(temp_project_dir),
        )

        model_data = {
            "model_metadata": {
                "metadata": {
                    "object_tags": {"sensitivity_tag": "pii", "classification": "public"},
                    "schema": [{"name": "id", "datatype": "INTEGER"}],
                }
            },
            "code": {
                "sql": {
                    "original_sql": "SELECT 1 as id",
                    "resolved_sql": "SELECT 1 as id",
                    "source_tables": [],
                }
            },
        }

        metadata_extractor = MetadataExtractor()
        metadata = metadata_extractor.extract_model_metadata(model_data)
        assert metadata is not None
        assert "object_tags" in metadata
        assert metadata["object_tags"]["sensitivity_tag"] == "pii"
        assert metadata["object_tags"]["classification"] == "public"

    def test_extract_both_tags_and_object_tags(self, temp_project_dir):
        """Test that both tags and object_tags can be extracted together."""
        ExecutionEngine(
            config={"type": "duckdb", "path": ":memory:"},
            project_folder=str(temp_project_dir),
        )

        model_data = {
            "model_metadata": {
                "metadata": {
                    "tags": ["analytics", "production"],  # dbt-style
                    "object_tags": {  # database-style
                        "sensitivity_tag": "pii",
                        "classification": "public",
                    },
                    "schema": [{"name": "id", "datatype": "INTEGER"}],
                }
            },
            "code": {
                "sql": {
                    "original_sql": "SELECT 1 as id",
                    "resolved_sql": "SELECT 1 as id",
                    "source_tables": [],
                }
            },
        }

        metadata_extractor = MetadataExtractor()
        metadata = metadata_extractor.extract_model_metadata(model_data)
        assert metadata is not None
        assert "tags" in metadata
        assert "object_tags" in metadata
        assert metadata["tags"] == ["analytics", "production"]
        assert metadata["object_tags"]["sensitivity_tag"] == "pii"
