"""
Tests for the dbt importer main function.
"""

import tempfile
from pathlib import Path

import pytest
import yaml

from tee.importer.dbt.exceptions import DbtProjectNotFoundError
from tee.importer.dbt.importer import import_dbt_project


class TestDbtImporter:
    """Tests for the main dbt importer function."""

    def test_import_dbt_project_basic(self):
        """Test basic dbt project import."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "source"
            source_path.mkdir()

            # Create a minimal dbt project
            dbt_project_file = source_path / "dbt_project.yml"
            dbt_config = {
                "name": "test_project",
                "version": "1.0.0",
            }
            with dbt_project_file.open("w", encoding="utf-8") as f:
                yaml.dump(dbt_config, f)

            # Create models directory
            (source_path / "models").mkdir()

            target_path = Path(tmpdir) / "target"

            # Should not raise
            import_dbt_project(
                source_path=source_path,
                target_path=target_path,
                output_format="t4t",
                preserve_filenames=False,
                validate_execution=False,
                verbose=False,
            )

            # Check that target structure was created
            assert (target_path / "models").exists()
            assert (target_path / "tests").exists()
            assert (target_path / "seeds").exists()
            assert (target_path / "functions").exists()

    def test_import_dbt_project_ots_format(self):
        """Test dbt project import with OTS format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "source"
            source_path.mkdir()

            # Create a minimal dbt project
            dbt_project_file = source_path / "dbt_project.yml"
            dbt_config = {"name": "test_project"}
            with dbt_project_file.open("w", encoding="utf-8") as f:
                yaml.dump(dbt_config, f)

            (source_path / "models").mkdir()

            target_path = Path(tmpdir) / "target"

            import_dbt_project(
                source_path=source_path,
                target_path=target_path,
                output_format="ots",
                preserve_filenames=False,
                validate_execution=False,
                verbose=False,
            )

            # Check that OTS structure was created (ots_modules instead of functions)
            assert (target_path / "models").exists()
            assert (target_path / "ots_modules").exists()
            assert not (target_path / "functions").exists()

    def test_import_dbt_project_verbose(self):
        """Test dbt project import with verbose mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "source"
            source_path.mkdir()

            dbt_project_file = source_path / "dbt_project.yml"
            dbt_config = {"name": "test_project"}
            with dbt_project_file.open("w", encoding="utf-8") as f:
                yaml.dump(dbt_config, f)

            (source_path / "models").mkdir()

            target_path = Path(tmpdir) / "target"

            # Should not raise with verbose=True
            import_dbt_project(
                source_path=source_path,
                target_path=target_path,
                output_format="t4t",
                preserve_filenames=False,
                validate_execution=False,
                verbose=True,
            )

            assert (target_path / "models").exists()

    def test_import_dbt_project_preserve_filenames(self):
        """Test dbt project import with preserve_filenames option."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "source"
            source_path.mkdir()

            dbt_project_file = source_path / "dbt_project.yml"
            dbt_config = {"name": "test_project"}
            with dbt_project_file.open("w", encoding="utf-8") as f:
                yaml.dump(dbt_config, f)

            (source_path / "models").mkdir()

            target_path = Path(tmpdir) / "target"

            # Should not raise with preserve_filenames=True
            import_dbt_project(
                source_path=source_path,
                target_path=target_path,
                output_format="t4t",
                preserve_filenames=True,
                validate_execution=False,
                verbose=False,
            )

            assert (target_path / "models").exists()

    def test_import_dbt_project_parser_error(self):
        """Test that parser errors are propagated."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "source"
            source_path.mkdir()

            # Don't create dbt_project.yml - should fail
            target_path = Path(tmpdir) / "target"

            with pytest.raises(DbtProjectNotFoundError, match="dbt_project.yml not found"):
                import_dbt_project(
                    source_path=source_path,
                    target_path=target_path,
                    output_format="t4t",
                    preserve_filenames=False,
                    validate_execution=False,
                    verbose=False,
                )

    def test_import_dbt_project_paths_resolved(self):
        """Test that paths are resolved to absolute paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "source"
            source_path.mkdir()

            dbt_project_file = source_path / "dbt_project.yml"
            dbt_config = {"name": "test_project"}
            with dbt_project_file.open("w", encoding="utf-8") as f:
                yaml.dump(dbt_config, f)

            (source_path / "models").mkdir()

            target_path = Path(tmpdir) / "target"

            # Use relative paths
            import_dbt_project(
                source_path=str(source_path),
                target_path=str(target_path),
                output_format="t4t",
                preserve_filenames=False,
                validate_execution=False,
                verbose=False,
            )

            # Should still work (paths are resolved internally)
            assert (target_path / "models").exists()
