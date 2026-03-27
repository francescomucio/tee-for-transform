"""
Unit tests for OTS format import functionality.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from tee.compiler import CompilationError
from tee.importer.dbt.importer import import_dbt_project


class TestOtsFormatImport:
    """Tests for OTS format import functionality."""

    def _create_minimal_dbt_project(self, source_path: Path) -> None:
        """Helper to create a minimal dbt project structure."""
        dbt_project_file = source_path / "dbt_project.yml"
        dbt_config = {
            "name": "test_project",
            "version": "1.0.0",
        }
        with dbt_project_file.open("w", encoding="utf-8") as f:
            yaml.dump(dbt_config, f)

        # Create models directory with a simple model
        models_dir = source_path / "models"
        models_dir.mkdir()
        model_file = models_dir / "customers.sql"
        model_file.write_text("SELECT 1 as id, 'test' as name")

    @patch("tee.compiler.compile_project")
    def test_ots_compilation_called_when_format_is_ots(self, mock_compile):
        """Test that compile_project is called when output_format is 'ots'."""
        mock_compile.return_value = {
            "ots_modules_count": 1,
            "parsed_models_count": 1,
            "parsed_functions": {},
            "output_folder": "output/ots_modules",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "source"
            source_path.mkdir()
            self._create_minimal_dbt_project(source_path)

            target_path = Path(tmpdir) / "target"

            import_dbt_project(
                source_path=source_path,
                target_path=target_path,
                output_format="ots",
                preserve_filenames=False,
                validate_execution=False,
                verbose=False,
            )

            # Verify compile_project was called
            assert mock_compile.called
            call_args = mock_compile.call_args
            assert call_args.kwargs["project_folder"] == str(target_path)
            assert "connection_config" in call_args.kwargs
            assert call_args.kwargs["format"] == "json"

    @patch("tee.compiler.compile_project")
    def test_ots_compilation_not_called_when_format_is_t4t(self, mock_compile):
        """Test that compile_project is NOT called when output_format is 't4t'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "source"
            source_path.mkdir()
            self._create_minimal_dbt_project(source_path)

            target_path = Path(tmpdir) / "target"

            import_dbt_project(
                source_path=source_path,
                target_path=target_path,
                output_format="t4t",
                preserve_filenames=False,
                validate_execution=False,
                verbose=False,
            )

            # Verify compile_project was NOT called
            assert not mock_compile.called

    @patch("tee.compiler.compile_project")
    def test_ots_compilation_skipped_in_dry_run(self, mock_compile):
        """Test that OTS compilation is skipped in dry-run mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "source"
            source_path.mkdir()
            self._create_minimal_dbt_project(source_path)

            target_path = Path(tmpdir) / "target"

            import_dbt_project(
                source_path=source_path,
                target_path=target_path,
                output_format="ots",
                preserve_filenames=False,
                validate_execution=False,
                verbose=False,
                dry_run=True,
            )

            # Verify compile_project was NOT called in dry-run
            assert not mock_compile.called

    @patch("tee.compiler.compile_project")
    def test_ots_compilation_success_included_in_reports(self, mock_compile):
        """Test that successful OTS compilation results are included in reports."""
        mock_compile.return_value = {
            "ots_modules_count": 2,
            "parsed_models_count": 1,
            "parsed_functions": {"func1": MagicMock()},
            "output_folder": "output/ots_modules",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "source"
            source_path.mkdir()
            self._create_minimal_dbt_project(source_path)

            target_path = Path(tmpdir) / "target"

            import_dbt_project(
                source_path=source_path,
                target_path=target_path,
                output_format="ots",
                preserve_filenames=False,
                validate_execution=False,
                verbose=False,
            )

            # Check that import report was generated
            report_file = target_path / "IMPORT_REPORT.md"
            assert report_file.exists()

            # Check that OTS compilation results are in the report
            report_content = report_file.read_text()
            assert "OTS Compilation Results" in report_content
            assert "OTS compilation successful" in report_content
            assert "OTS Modules Generated" in report_content

            # Check JSON log
            log_file = target_path / "CONVERSION_LOG.json"
            assert log_file.exists()

            import json

            log_data = json.loads(log_file.read_text())
            assert "ots_compilation" in log_data
            assert log_data["ots_compilation"]["success"] is True
            assert log_data["ots_compilation"]["ots_modules_count"] == 2

    @patch("tee.compiler.compile_project")
    def test_ots_compilation_error_handled_gracefully(self, mock_compile):
        """Test that OTS compilation errors are handled gracefully."""
        mock_compile.side_effect = CompilationError("Test compilation error")

        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "source"
            source_path.mkdir()
            self._create_minimal_dbt_project(source_path)

            target_path = Path(tmpdir) / "target"

            # Should not raise, but log the error
            import_dbt_project(
                source_path=source_path,
                target_path=target_path,
                output_format="ots",
                preserve_filenames=False,
                validate_execution=False,
                verbose=False,
            )

            # Check that import report was generated with error info
            report_file = target_path / "IMPORT_REPORT.md"
            assert report_file.exists()

            report_content = report_file.read_text()
            assert "OTS Compilation Results" in report_content
            assert "OTS compilation failed" in report_content
            assert "Test compilation error" in report_content

            # Check JSON log
            import json

            log_file = target_path / "CONVERSION_LOG.json"
            log_data = json.loads(log_file.read_text())
            assert "ots_compilation" in log_data
            assert log_data["ots_compilation"]["success"] is False
            assert "error" in log_data["ots_compilation"]

    @patch("tee.compiler.compile_project")
    def test_ots_compilation_generic_error_handled(self, mock_compile):
        """Test that generic exceptions during OTS compilation are handled."""
        mock_compile.side_effect = ValueError("Unexpected error")

        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "source"
            source_path.mkdir()
            self._create_minimal_dbt_project(source_path)

            target_path = Path(tmpdir) / "target"

            # Should not raise
            import_dbt_project(
                source_path=source_path,
                target_path=target_path,
                output_format="ots",
                preserve_filenames=False,
                validate_execution=False,
                verbose=False,
            )

            # Check that error is logged
            import json

            log_file = target_path / "CONVERSION_LOG.json"
            log_data = json.loads(log_file.read_text())
            assert "ots_compilation" in log_data
            assert log_data["ots_compilation"]["success"] is False

    @patch("tee.compiler.compile_project")
    def test_ots_compilation_uses_connection_config(self, mock_compile):
        """Test that connection_config is passed to compile_project."""
        mock_compile.return_value = {
            "ots_modules_count": 1,
            "parsed_models_count": 1,
            "parsed_functions": {},
            "output_folder": "output/ots_modules",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "source"
            source_path.mkdir()
            self._create_minimal_dbt_project(source_path)

            target_path = Path(tmpdir) / "target"

            import_dbt_project(
                source_path=source_path,
                target_path=target_path,
                output_format="ots",
                preserve_filenames=False,
                validate_execution=False,
                verbose=False,
            )

            # Verify connection_config was passed
            call_args = mock_compile.call_args
            assert "connection_config" in call_args.kwargs
            # Should have a connection config (either from profiles or default DuckDB)
            connection_config = call_args.kwargs["connection_config"]
            assert "type" in connection_config

    @patch("tee.compiler.compile_project")
    def test_ots_compilation_loads_project_config(self, mock_compile):
        """Test that project.toml is loaded and passed to compile_project."""
        mock_compile.return_value = {
            "ots_modules_count": 1,
            "parsed_models_count": 1,
            "parsed_functions": {},
            "output_folder": "output/ots_modules",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "source"
            source_path.mkdir()
            self._create_minimal_dbt_project(source_path)

            target_path = Path(tmpdir) / "target"

            import_dbt_project(
                source_path=source_path,
                target_path=target_path,
                output_format="ots",
                preserve_filenames=False,
                validate_execution=False,
                verbose=False,
            )

            # Verify project_config was passed (may be None if project.toml doesn't exist yet)
            call_args = mock_compile.call_args
            assert "project_config" in call_args.kwargs
            # project_config can be None if project.toml doesn't exist, which is fine

    @patch("tee.compiler.compile_project")
    def test_ots_compilation_summary_in_report(self, mock_compile):
        """Test that OTS compilation summary is included in the summary section."""
        mock_compile.return_value = {
            "ots_modules_count": 3,
            "parsed_models_count": 2,
            "parsed_functions": {},
            "output_folder": "output/ots_modules",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "source"
            source_path.mkdir()
            self._create_minimal_dbt_project(source_path)

            target_path = Path(tmpdir) / "target"

            import_dbt_project(
                source_path=source_path,
                target_path=target_path,
                output_format="ots",
                preserve_filenames=False,
                validate_execution=False,
                verbose=False,
            )

            # Check summary section includes OTS compilation status
            report_file = target_path / "IMPORT_REPORT.md"
            report_content = report_file.read_text()

            # Check summary table includes OTS compilation
            assert "OTS Compilation Status" in report_content
            assert "OTS Modules Generated" in report_content
            assert "3" in report_content  # ots_modules_count
