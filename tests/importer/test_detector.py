"""
Tests for the project type detector.
"""

import tempfile
from pathlib import Path

import yaml

from t4t.importer.detector import ProjectType, detect_project_type


class TestProjectTypeDetector:
    """Tests for project type detection."""

    def test_detect_dbt_project(self):
        """Test detection of dbt project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create dbt_project.yml
            dbt_project_file = tmpdir_path / "dbt_project.yml"
            dbt_config = {
                "name": "test_project",
                "version": "1.0.0",
            }
            with dbt_project_file.open("w", encoding="utf-8") as f:
                yaml.dump(dbt_config, f)

            # Create models directory
            models_dir = tmpdir_path / "models"
            models_dir.mkdir()

            project_type = detect_project_type(tmpdir_path)
            assert project_type == ProjectType.DBT

    def test_detect_dbt_project_without_models_dir(self):
        """Test detection of dbt project without models directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create dbt_project.yml
            dbt_project_file = tmpdir_path / "dbt_project.yml"
            dbt_config = {
                "name": "test_project",
                "version": "1.0.0",
            }
            with dbt_project_file.open("w", encoding="utf-8") as f:
                yaml.dump(dbt_config, f)

            project_type = detect_project_type(tmpdir_path)
            assert project_type == ProjectType.DBT

    def test_detect_unknown_project(self):
        """Test detection of unknown project type."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a random file (not dbt_project.yml)
            random_file = tmpdir_path / "random.yml"
            random_file.write_text("test: value")

            project_type = detect_project_type(tmpdir_path)
            assert project_type == ProjectType.UNKNOWN

    def test_detect_nonexistent_path(self):
        """Test detection with nonexistent path."""
        nonexistent_path = Path("/nonexistent/path/that/does/not/exist")
        project_type = detect_project_type(nonexistent_path)
        assert project_type == ProjectType.UNKNOWN

    def test_detect_invalid_dbt_project_yml(self):
        """Test detection with invalid dbt_project.yml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create invalid dbt_project.yml (not a dict, missing name)
            dbt_project_file = tmpdir_path / "dbt_project.yml"
            dbt_project_file.write_text("not a valid yaml dict")

            project_type = detect_project_type(tmpdir_path)
            assert project_type == ProjectType.UNKNOWN

    def test_detect_dbt_project_missing_name(self):
        """Test detection of dbt project missing name field."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create dbt_project.yml without name
            dbt_project_file = tmpdir_path / "dbt_project.yml"
            dbt_config = {
                "version": "1.0.0",
            }
            with dbt_project_file.open("w", encoding="utf-8") as f:
                yaml.dump(dbt_config, f)

            project_type = detect_project_type(tmpdir_path)
            assert project_type == ProjectType.UNKNOWN
