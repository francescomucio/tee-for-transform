"""
Tests for project.toml generator.
"""

import tempfile
from pathlib import Path

from t4t.importer.dbt.generators import ProjectConfigGenerator


class TestProjectConfigGenerator:
    """Tests for ProjectConfigGenerator."""

    def test_generate_project_toml_basic(self):
        """Test generating basic project.toml."""
        generator = ProjectConfigGenerator(verbose=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir) / "target"
            target_path.mkdir()

            dbt_project = {"name": "test_project"}

            generator.generate_project_toml(
                target_path=target_path,
                dbt_project=dbt_project,
                connection_config=None,
                packages_info=None,
            )

            project_toml = target_path / "project.toml"
            assert project_toml.exists()

            content = project_toml.read_text()
            assert 'project_folder = "target"' in content
            assert "[connection]" in content
            assert 'type = "duckdb"' in content
            assert "[flags]" in content

    def test_generate_project_toml_with_connection(self):
        """Test generating project.toml with connection config."""
        generator = ProjectConfigGenerator(verbose=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir) / "target"
            target_path.mkdir()

            dbt_project = {"name": "test_project"}
            connection_config = {
                "type": "postgresql",
                "host": "localhost",
                "port": 5432,
                "database": "mydb",
                "user": "myuser",
                "password": "mypass",
            }

            generator.generate_project_toml(
                target_path=target_path,
                dbt_project=dbt_project,
                connection_config=connection_config,
                packages_info=None,
            )

            project_toml = target_path / "project.toml"
            content = project_toml.read_text()
            assert 'type = "postgresql"' in content
            assert 'host = "localhost"' in content
            assert "port = 5432" in content
            assert 'database = "mydb"' in content

    def test_generate_project_toml_with_packages(self):
        """Test generating project.toml with packages info."""
        generator = ProjectConfigGenerator(verbose=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir) / "target"
            target_path.mkdir()

            dbt_project = {"name": "test_project"}
            packages_info = {
                "has_packages": True,
                "packages": [
                    {"package": "dbt-utils", "version": "1.0.0"},
                    {"package": "dbt-date", "version": "0.7.0"},
                ],
            }

            generator.generate_project_toml(
                target_path=target_path,
                dbt_project=dbt_project,
                connection_config=None,
                packages_info=packages_info,
            )

            project_toml = target_path / "project.toml"
            content = project_toml.read_text()
            assert "# Note: This project uses dbt packages:" in content
            assert "#   - dbt-utils (version: 1.0.0)" in content
            assert "#   - dbt-date (version: 0.7.0)" in content
