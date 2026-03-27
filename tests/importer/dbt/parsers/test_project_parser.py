"""
Tests for the dbt project parser.
"""

import tempfile
from pathlib import Path

import pytest
import yaml

from tee.importer.dbt.exceptions import DbtProjectNotFoundError
from tee.importer.dbt.parsers import DbtProjectParser


class TestDbtProjectParser:
    """Tests for dbt project parser."""

    def test_parse_valid_dbt_project(self):
        """Test parsing a valid dbt project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create dbt_project.yml
            dbt_project_file = tmpdir_path / "dbt_project.yml"
            dbt_config = {
                "name": "test_project",
                "version": "1.0.0",
                "profile-name": "my_profile",
                "model-paths": ["models"],
                "test-paths": ["tests"],
                "seed-paths": ["seeds"],
                "macro-paths": ["macros"],
                "vars": {
                    "env": "dev",
                },
            }
            with dbt_project_file.open("w", encoding="utf-8") as f:
                yaml.dump(dbt_config, f)

            # Create models directory
            models_dir = tmpdir_path / "models"
            models_dir.mkdir()

            parser = DbtProjectParser(tmpdir_path)
            result = parser.parse()

            assert result["name"] == "test_project"
            assert result["version"] == "1.0.0"
            assert result["profile"] == "my_profile"
            assert result["model-paths"] == ["models"]
            assert result["vars"] == {"env": "dev"}

    def test_parse_dbt_project_with_defaults(self):
        """Test parsing dbt project with default values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create minimal dbt_project.yml
            dbt_project_file = tmpdir_path / "dbt_project.yml"
            dbt_config = {
                "name": "test_project",
            }
            with dbt_project_file.open("w", encoding="utf-8") as f:
                yaml.dump(dbt_config, f)

            # Create models directory
            models_dir = tmpdir_path / "models"
            models_dir.mkdir()

            parser = DbtProjectParser(tmpdir_path)
            result = parser.parse()

            assert result["name"] == "test_project"
            assert result["model-paths"] == ["models"]  # default
            assert result["test-paths"] == ["tests"]  # default
            assert result["seed-paths"] == ["seeds"]  # default
            assert result["config-version"] == 2  # default

    def test_parse_missing_dbt_project_yml(self):
        """Test parsing when dbt_project.yml is missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Parser raises error during initialization when dbt_project.yml is missing
            with pytest.raises(DbtProjectNotFoundError, match="dbt_project.yml not found"):
                DbtProjectParser(tmpdir_path)

    def test_parse_invalid_yaml(self):
        """Test parsing invalid YAML."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create invalid YAML file
            dbt_project_file = tmpdir_path / "dbt_project.yml"
            dbt_project_file.write_text("invalid: yaml: content: [")

            parser = DbtProjectParser(tmpdir_path)

            # Should raise an error when trying to parse
            with pytest.raises((ValueError, yaml.YAMLError)):
                parser.parse()

    def test_parse_missing_name_field(self):
        """Test parsing dbt project missing required name field."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create dbt_project.yml without name
            dbt_project_file = tmpdir_path / "dbt_project.yml"
            dbt_config = {
                "version": "1.0.0",
            }
            with dbt_project_file.open("w", encoding="utf-8") as f:
                yaml.dump(dbt_config, f)

            parser = DbtProjectParser(tmpdir_path)

            with pytest.raises(DbtProjectNotFoundError, match="missing required 'name' field"):
                parser.parse()

    def test_parse_non_dict_yaml(self):
        """Test parsing YAML that is not a dictionary."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create YAML that's not a dict
            dbt_project_file = tmpdir_path / "dbt_project.yml"
            dbt_project_file.write_text("- item1\n- item2")

            parser = DbtProjectParser(tmpdir_path)

            with pytest.raises(DbtProjectNotFoundError, match="not a valid YAML dictionary"):
                parser.parse()

    def test_validate_structure_with_directories(self):
        """Test structure validation with common directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create dbt_project.yml
            dbt_project_file = tmpdir_path / "dbt_project.yml"
            dbt_config = {"name": "test_project"}
            with dbt_project_file.open("w", encoding="utf-8") as f:
                yaml.dump(dbt_config, f)

            # Create multiple directories
            (tmpdir_path / "models").mkdir()
            (tmpdir_path / "tests").mkdir()
            (tmpdir_path / "macros").mkdir()

            parser = DbtProjectParser(tmpdir_path, verbose=True)
            # Should not raise
            result = parser.parse()
            assert result["name"] == "test_project"
