"""
Tests for OTS module reader.
"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from tee.parser.input import OTSModuleReader, OTSModuleReaderError


class TestOTSModuleReader:
    """Tests for OTSModuleReader."""

    def test_read_valid_module(self):
        """Test reading a valid OTS module."""
        reader = OTSModuleReader()

        # Create a minimal valid OTS module
        module_data = {
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
                            "original_sql": "SELECT 1 as col1",
                            "resolved_sql": "SELECT 1 as col1",
                            "source_tables": [],
                        }
                    },
                }
            ],
        }

        with TemporaryDirectory() as tmpdir:
            module_file = Path(tmpdir) / "test.ots.json"
            with open(module_file, "w") as f:
                json.dump(module_data, f)

            module = reader.read_module(module_file)
            assert module["module_name"] == "test.module"
            assert len(module["transformations"]) == 1

    def test_read_module_missing_required_field(self):
        """Test reading a module with missing required field."""
        reader = OTSModuleReader()

        # Missing target field
        module_data = {
            "ots_version": "0.1.0",
            "module_name": "test.module",
            "transformations": [],
        }

        with TemporaryDirectory() as tmpdir:
            module_file = Path(tmpdir) / "test.ots.json"
            with open(module_file, "w") as f:
                json.dump(module_data, f)

            with pytest.raises(OTSModuleReaderError):
                reader.read_module(module_file)

    def test_read_module_invalid_json(self):
        """Test reading a module with invalid JSON."""
        reader = OTSModuleReader()

        with TemporaryDirectory() as tmpdir:
            module_file = Path(tmpdir) / "test.ots.json"
            with open(module_file, "w") as f:
                f.write("invalid json {")

            with pytest.raises(OTSModuleReaderError):
                reader.read_module(module_file)

    def test_read_module_nonexistent_file(self):
        """Test reading a nonexistent file."""
        reader = OTSModuleReader()
        nonexistent_file = Path("/nonexistent/path/to/module.ots.json")

        with pytest.raises(OTSModuleReaderError):
            reader.read_module(nonexistent_file)

    def test_read_modules_from_directory(self):
        """Test reading multiple modules from a directory."""
        reader = OTSModuleReader()

        module_data = {
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
                            "original_sql": "SELECT 1 as col1",
                            "resolved_sql": "SELECT 1 as col1",
                            "source_tables": [],
                        }
                    },
                }
            ],
        }

        with TemporaryDirectory() as tmpdir:
            # Create two module files
            module_file1 = Path(tmpdir) / "module1.ots.json"
            module_file2 = Path(tmpdir) / "module2.ots.json"

            with open(module_file1, "w") as f:
                json.dump({**module_data, "module_name": "module1"}, f)
            with open(module_file2, "w") as f:
                json.dump({**module_data, "module_name": "module2"}, f)

            modules = reader.read_modules_from_directory(Path(tmpdir))
            assert len(modules) == 2
            assert "module1" in modules
            assert "module2" in modules

    def test_get_module_info(self):
        """Test getting module information."""
        reader = OTSModuleReader()

        module_data = {
            "ots_version": "0.2.2",
            "module_name": "test.module",
            "module_description": "Test module",
            "version": "1.0.0",
            "tags": ["tag1", "tag2"],
            "test_library_path": "test_library.ots.json",
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
                }
            ],
        }

        info = reader.get_module_info(module_data)
        assert info["module_name"] == "test.module"
        assert info["ots_version"] == "0.2.2"
        assert info["transformation_count"] == 1
        assert info["has_test_library"] is True
        assert len(info["module_tags"]) == 2
