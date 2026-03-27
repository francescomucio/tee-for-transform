"""
Tests for the source parser.
"""

import tempfile
from pathlib import Path

import yaml

from tee.importer.dbt.parsers import SourceParser


class TestSourceParser:
    """Tests for source parser."""

    def test_parse_source_file_simple(self):
        """Test parsing a simple __sources.yml file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_file = Path(tmpdir) / "__sources.yml"
            source_content = {
                "sources": [
                    {
                        "name": "raw",
                        "schema": "raw_schema",
                        "tables": [
                            {"name": "users"},
                            {"name": "orders"},
                        ],
                    }
                ]
            }
            with source_file.open("w", encoding="utf-8") as f:
                yaml.dump(source_content, f)

            parser = SourceParser()
            sources = parser.parse_source_file(source_file)

            assert "raw" in sources
            assert "users" in sources["raw"]
            assert "orders" in sources["raw"]
            assert sources["raw"]["users"] == "raw_schema.users"
            assert sources["raw"]["orders"] == "raw_schema.orders"

    def test_parse_source_file_default_schema(self):
        """Test parsing source file with default schema (source name)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_file = Path(tmpdir) / "__sources.yml"
            source_content = {
                "sources": [
                    {
                        "name": "raw",
                        "tables": [
                            {"name": "users"},
                        ],
                    }
                ]
            }
            with source_file.open("w", encoding="utf-8") as f:
                yaml.dump(source_content, f)

            parser = SourceParser()
            sources = parser.parse_source_file(source_file)

            assert "raw" in sources
            assert sources["raw"]["users"] == "raw.users"  # Default to source name

    def test_parse_source_file_multiple_sources(self):
        """Test parsing source file with multiple sources."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_file = Path(tmpdir) / "__sources.yml"
            source_content = {
                "sources": [
                    {
                        "name": "raw",
                        "schema": "raw_schema",
                        "tables": [{"name": "users"}],
                    },
                    {
                        "name": "staging",
                        "schema": "staging_schema",
                        "tables": [{"name": "orders"}],
                    },
                ]
            }
            with source_file.open("w", encoding="utf-8") as f:
                yaml.dump(source_content, f)

            parser = SourceParser()
            sources = parser.parse_source_file(source_file)

            assert len(sources) == 2
            assert "raw" in sources
            assert "staging" in sources
            assert sources["raw"]["users"] == "raw_schema.users"
            assert sources["staging"]["orders"] == "staging_schema.orders"

    def test_parse_source_file_invalid_yaml(self):
        """Test parsing invalid YAML file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_file = Path(tmpdir) / "__sources.yml"
            source_file.write_text("invalid: yaml: content: [")

            parser = SourceParser()
            sources = parser.parse_source_file(source_file)

            # Should return empty dict on error
            assert sources == {}

    def test_parse_source_file_not_dict(self):
        """Test parsing YAML that is not a dictionary."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_file = Path(tmpdir) / "__sources.yml"
            source_file.write_text("- item1\n- item2")

            parser = SourceParser()
            sources = parser.parse_source_file(source_file)

            # Should return empty dict
            assert sources == {}

    def test_parse_source_file_no_sources_key(self):
        """Test parsing source file without sources key."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_file = Path(tmpdir) / "__sources.yml"
            source_content = {"models": [{"name": "customers"}]}
            with source_file.open("w", encoding="utf-8") as f:
                yaml.dump(source_content, f)

            parser = SourceParser()
            sources = parser.parse_source_file(source_file)

            # Should return empty dict
            assert sources == {}

    def test_parse_source_file_invalid_source_format(self):
        """Test parsing source file with invalid source format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_file = Path(tmpdir) / "__sources.yml"
            source_content = {
                "sources": [
                    "not a dict",
                    {"name": "valid_source", "tables": [{"name": "table1"}]},
                    {"no_name": "invalid"},
                ]
            }
            with source_file.open("w", encoding="utf-8") as f:
                yaml.dump(source_content, f)

            parser = SourceParser()
            sources = parser.parse_source_file(source_file)

            # Should only include valid source
            assert len(sources) == 1
            assert "valid_source" in sources

    def test_parse_source_file_invalid_table_format(self):
        """Test parsing source file with invalid table format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_file = Path(tmpdir) / "__sources.yml"
            source_content = {
                "sources": [
                    {
                        "name": "raw",
                        "tables": [
                            "not a dict",
                            {"name": "valid_table"},
                            {"no_name": "invalid"},
                        ],
                    }
                ]
            }
            with source_file.open("w", encoding="utf-8") as f:
                yaml.dump(source_content, f)

            parser = SourceParser()
            sources = parser.parse_source_file(source_file)

            # Should only include valid table
            assert len(sources["raw"]) == 1
            assert "valid_table" in sources["raw"]

    def test_parse_all_source_files(self):
        """Test parsing multiple source files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_file1 = Path(tmpdir) / "__sources1.yml"
            source_file2 = Path(tmpdir) / "__sources2.yml"

            source_content1 = {
                "sources": [
                    {
                        "name": "raw",
                        "schema": "raw_schema",
                        "tables": [{"name": "users"}],
                    }
                ]
            }
            source_content2 = {
                "sources": [
                    {
                        "name": "staging",
                        "schema": "staging_schema",
                        "tables": [{"name": "orders"}],
                    }
                ]
            }

            with source_file1.open("w", encoding="utf-8") as f:
                yaml.dump(source_content1, f)
            with source_file2.open("w", encoding="utf-8") as f:
                yaml.dump(source_content2, f)

            parser = SourceParser()
            source_files = [source_file1, source_file2]
            sources = parser.parse_all_source_files(source_files)

            assert len(sources) == 2
            assert "raw" in sources
            assert "staging" in sources

    def test_parse_all_source_files_merge_tables(self):
        """Test that parsing multiple files merges tables for same source."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_file1 = Path(tmpdir) / "__sources1.yml"
            source_file2 = Path(tmpdir) / "__sources2.yml"

            source_content1 = {
                "sources": [
                    {
                        "name": "raw",
                        "schema": "raw_schema",
                        "tables": [{"name": "users"}],
                    }
                ]
            }
            source_content2 = {
                "sources": [
                    {
                        "name": "raw",
                        "schema": "raw_schema",
                        "tables": [{"name": "orders"}],
                    }
                ]
            }

            with source_file1.open("w", encoding="utf-8") as f:
                yaml.dump(source_content1, f)
            with source_file2.open("w", encoding="utf-8") as f:
                yaml.dump(source_content2, f)

            parser = SourceParser()
            source_files = [source_file1, source_file2]
            sources = parser.parse_all_source_files(source_files)

            assert len(sources) == 1
            assert "raw" in sources
            assert len(sources["raw"]) == 2
            assert "users" in sources["raw"]
            assert "orders" in sources["raw"]

    def test_parse_source_file_verbose(self):
        """Test parsing with verbose mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_file = Path(tmpdir) / "__sources.yml"
            source_content = {
                "sources": [
                    {
                        "name": "raw",
                        "tables": [{"name": "users"}],
                    }
                ]
            }
            with source_file.open("w", encoding="utf-8") as f:
                yaml.dump(source_content, f)

            parser = SourceParser(verbose=True)
            sources = parser.parse_source_file(source_file)

            assert "raw" in sources
