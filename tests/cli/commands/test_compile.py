"""
Unit tests for the compile CLI command.
"""

import contextlib
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from t4t.cli.commands.compile import cmd_compile


class TestCompileCommand:
    """Test cases for the compile CLI command."""

    @pytest.fixture
    def temp_project_dir(self):
        """Create a temporary project directory with project.toml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            # Create project.toml
            project_toml = tmpdir_path / "project.toml"
            project_toml.write_text(
                'project_folder = "test"\n[connection]\ntype = "duckdb"\npath = ":memory:"'
            )
            yield tmpdir_path

    @pytest.fixture
    def mock_args(self, temp_project_dir):
        """Create mock CLI arguments."""
        args = MagicMock()
        args.project_folder = str(temp_project_dir)
        args.vars = None
        args.verbose = False
        args.format = "json"
        return args

    @patch("t4t.cli.commands.compile.compile_project")
    @patch("t4t.cli.commands.compile.CommandContext")
    def test_cmd_compile_success(self, mock_context_class, mock_compile, mock_args):
        """Test successful compile command execution."""
        # Setup mocks
        mock_ctx = Mock()
        mock_ctx.project_path = Path(mock_args.project_folder)
        mock_ctx.vars = {}
        mock_ctx.config = {"connection": {"type": "duckdb", "path": ":memory:"}}
        mock_ctx.print_variables_info = Mock()
        mock_context_class.return_value = mock_ctx

        mock_compile.return_value = {
            "parsed_models_count": 2,
            "imported_ots_count": 1,
            "total_transformations": 3,
            "ots_modules_count": 2,
            "output_folder": "output/ots_modules",
        }

        # Capture stdout
        with patch("sys.stdout", new=StringIO()) as fake_out:
            cmd_compile(
                project_folder=mock_args.project_folder,
                vars=mock_args.vars,
                verbose=mock_args.verbose,
                format=mock_args.format,
            )

        output = fake_out.getvalue()
        assert "Compiling project:" in output
        assert "Compilation complete!" in output
        assert "Parsed models: 2" in output
        assert "Imported OTS: 1" in output

        # Verify compile_project was called with correct arguments
        mock_compile.assert_called_once_with(
            project_folder=str(mock_ctx.project_path),
            connection_config=mock_ctx.config["connection"],
            variables=mock_ctx.vars,
            project_config=mock_ctx.config,
            format="json",
        )

    @patch("t4t.cli.commands.compile.compile_project")
    @patch("t4t.cli.commands.compile.CommandContext")
    def test_cmd_compile_yaml_format(self, mock_context_class, mock_compile, mock_args):
        """Test compile command with YAML format."""
        # Setup mocks
        mock_ctx = Mock()
        mock_ctx.project_path = Path(mock_args.project_folder)
        mock_ctx.vars = {}
        mock_ctx.config = {"connection": {"type": "duckdb", "path": ":memory:"}}
        mock_ctx.print_variables_info = Mock()
        mock_context_class.return_value = mock_ctx

        mock_compile.return_value = {
            "parsed_models_count": 1,
            "imported_ots_count": 0,
            "total_transformations": 1,
            "ots_modules_count": 1,
            "output_folder": "output/ots_modules",
        }

        # Capture stdout
        with patch("sys.stdout", new=StringIO()):
            cmd_compile(
                project_folder=mock_args.project_folder,
                vars=mock_args.vars,
                verbose=mock_args.verbose,
                format="yaml",
            )

        # Verify compile_project was called with yaml format
        mock_compile.assert_called_once_with(
            project_folder=str(mock_ctx.project_path),
            connection_config=mock_ctx.config["connection"],
            variables=mock_ctx.vars,
            project_config=mock_ctx.config,
            format="yaml",
        )

    @patch("t4t.cli.commands.compile.compile_project")
    @patch("t4t.cli.commands.compile.CommandContext")
    def test_cmd_compile_error_handling(self, mock_context_class, mock_compile, mock_args):
        """Test compile command error handling."""
        from t4t.compiler import CompilationError

        # Setup mocks
        mock_ctx = Mock()
        mock_ctx.project_path = Path(mock_args.project_folder)
        mock_ctx.vars = {}
        mock_ctx.config = {"connection": {"type": "duckdb", "path": ":memory:"}}
        mock_ctx.print_variables_info = Mock()
        mock_ctx.handle_error = Mock()
        mock_context_class.return_value = mock_ctx

        mock_compile.side_effect = CompilationError("Test compilation error")

        # Capture both stdout and stderr (typer.echo with err=True writes to stderr)
        with (
            patch("sys.stdout", new=StringIO()) as fake_out,
            patch("sys.stderr", new=StringIO()) as fake_err,
            contextlib.suppress(SystemExit),
        ):  # expected from handle_error
            cmd_compile(
                project_folder=mock_args.project_folder,
                vars=mock_args.vars,
                verbose=mock_args.verbose,
                format=mock_args.format,
            )

        output = fake_out.getvalue() + fake_err.getvalue()
        assert "Compilation failed:" in output
        mock_ctx.handle_error.assert_called_once()
