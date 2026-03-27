"""
Tests for the import CLI command.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import typer

from tee.cli.commands.import_cmd import cmd_import


class TestImportCommand:
    """Tests for the import CLI command."""

    def test_import_nonexistent_source(self):
        """Test import with nonexistent source path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir) / "target"

            with pytest.raises(typer.Exit) as exc_info:
                cmd_import(
                    source_project_folder="/nonexistent/path",
                    target_project_folder=str(target_path),
                    format="t4t",
                    preserve_filenames=False,
                    validate_execution=False,
                    verbose=False,
                    dry_run=False,
                )

            assert exc_info.value.exit_code == 1

    def test_import_dry_run(self):
        """Test import with dry run mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "source"
            source_path.mkdir()

            # Create a fake dbt_project.yml
            dbt_project_file = source_path / "dbt_project.yml"
            dbt_project_file.write_text("name: test_project\n")

            target_path = Path(tmpdir) / "target"

            # Should not raise in dry run mode
            cmd_import(
                source_project_folder=str(source_path),
                target_project_folder=str(target_path),
                format="t4t",
                preserve_filenames=False,
                validate_execution=False,
                verbose=False,
                dry_run=True,
            )

            # Target should not exist in dry run
            assert not target_path.exists()

    def test_import_unknown_project_type(self):
        """Test import with unknown project type."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "source"
            source_path.mkdir()

            # Create a file that's not dbt_project.yml
            random_file = source_path / "random.yml"
            random_file.write_text("test: value")

            target_path = Path(tmpdir) / "target"

            with pytest.raises(typer.Exit) as exc_info:
                cmd_import(
                    source_project_folder=str(source_path),
                    target_project_folder=str(target_path),
                    format="t4t",
                    preserve_filenames=False,
                    validate_execution=False,
                    verbose=False,
                    dry_run=False,
                )

            assert exc_info.value.exit_code == 1

    @patch("tee.importer.dbt.importer.import_dbt_project")
    def test_import_dbt_project(self, mock_import):
        """Test import of dbt project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "source"
            source_path.mkdir()

            # Create a fake dbt_project.yml
            dbt_project_file = source_path / "dbt_project.yml"
            dbt_project_file.write_text("name: test_project\n")

            # Create models directory
            (source_path / "models").mkdir()

            target_path = Path(tmpdir) / "target"

            cmd_import(
                source_project_folder=str(source_path),
                target_project_folder=str(target_path),
                format="t4t",
                preserve_filenames=False,
                validate_execution=False,
                verbose=False,
                dry_run=False,
            )

            # Should call the dbt importer
            mock_import.assert_called_once()
            call_args = mock_import.call_args
            assert call_args.kwargs["output_format"] == "t4t"
            assert call_args.kwargs["preserve_filenames"] is False
            assert call_args.kwargs["validate_execution"] is False
            assert call_args.kwargs["verbose"] is False

    @patch("tee.importer.dbt.importer.import_dbt_project")
    def test_import_dbt_project_with_options(self, mock_import):
        """Test import of dbt project with all options."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "source"
            source_path.mkdir()

            # Create a fake dbt_project.yml
            dbt_project_file = source_path / "dbt_project.yml"
            dbt_project_file.write_text("name: test_project\n")

            # Create models directory
            (source_path / "models").mkdir()

            target_path = Path(tmpdir) / "target"

            cmd_import(
                source_project_folder=str(source_path),
                target_project_folder=str(target_path),
                format="ots",
                preserve_filenames=True,
                validate_execution=True,
                verbose=True,
                dry_run=False,
            )

            # Should call the dbt importer with all options
            mock_import.assert_called_once()
            call_args = mock_import.call_args
            assert call_args.kwargs["output_format"] == "ots"
            assert call_args.kwargs["preserve_filenames"] is True
            assert call_args.kwargs["validate_execution"] is True
            assert call_args.kwargs["verbose"] is True

    @patch("tee.importer.dbt.importer.import_dbt_project")
    def test_import_dbt_project_with_default_schema_and_dialect(self, mock_import):
        """Test import of dbt project with default_schema and target_dialect options."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "source"
            source_path.mkdir()

            # Create a fake dbt_project.yml
            dbt_project_file = source_path / "dbt_project.yml"
            dbt_project_file.write_text("name: test_project\n")

            # Create models directory
            (source_path / "models").mkdir()

            target_path = Path(tmpdir) / "target"

            cmd_import(
                source_project_folder=str(source_path),
                target_project_folder=str(target_path),
                format="t4t",
                preserve_filenames=False,
                validate_execution=False,
                verbose=False,
                dry_run=False,
                keep_jinja=False,
                default_schema="custom_schema",
                target_dialect="snowflake",
            )

            # Should call the dbt importer with new options
            mock_import.assert_called_once()
            call_args = mock_import.call_args
            assert call_args.kwargs["default_schema"] == "custom_schema"
            assert call_args.kwargs["target_dialect"] == "snowflake"
