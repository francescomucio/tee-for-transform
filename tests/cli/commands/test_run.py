"""
Tests for the run CLI command.
"""

import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from tee.cli.commands.run import cmd_run


class TestRunCommand:
    """Tests for the run CLI command."""

    @pytest.fixture(autouse=True)
    def mock_lookup_generation(self):
        """Prevent lookup generator side effects in unit tests."""
        with patch("tee.cli.commands.run.generate_lookups"):
            yield

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
        args.select = None
        args.exclude = None
        return args

    @patch("tee.cli.commands.run.execute_models")
    @patch("tee.cli.commands.run.ConnectionManager")
    @patch("tee.cli.commands.run.CommandContext")
    def test_cmd_run_success(
        self, mock_context_class, mock_connection_manager_class, mock_execute_models, mock_args
    ):
        """Test successful run command execution."""
        # Setup mocks
        mock_ctx = Mock()
        mock_ctx.project_path = Path(mock_args.project_folder)
        mock_ctx.vars = {}
        mock_ctx.select_patterns = None
        mock_ctx.exclude_patterns = None
        mock_ctx.config = {"connection": {"type": "duckdb", "path": ":memory:"}}
        mock_ctx.print_variables_info = Mock()
        mock_ctx.print_selection_info = Mock()
        mock_context_class.return_value = mock_ctx

        mock_connection_manager = Mock()
        mock_connection_manager_class.return_value = mock_connection_manager

        # Mock successful execution results
        mock_execute_models.return_value = {
            "executed_tables": ["schema1.table1", "schema1.table2"],
            "failed_tables": [],
            "warnings": [],
        }

        # Capture stdout
        with patch("sys.stdout", new=StringIO()) as fake_out:
            cmd_run(mock_args)

        output = fake_out.getvalue()
        assert "Running t4t on project:" in output
        assert "Completed!" in output
        assert "All 2 tables executed successfully!" in output

        # Verify execute_models was called correctly
        mock_execute_models.assert_called_once_with(
            project_folder=str(mock_ctx.project_path),
            connection_config=mock_ctx.config["connection"],
            save_analysis=True,
            variables={},
            select_patterns=None,
            exclude_patterns=None,
            project_config=mock_ctx.config,
        )

    @patch("tee.cli.commands.run.execute_models")
    @patch("tee.cli.commands.run.ConnectionManager")
    @patch("tee.cli.commands.run.CommandContext")
    def test_cmd_run_with_failures(
        self, mock_context_class, mock_connection_manager_class, mock_execute_models, mock_args
    ):
        """Test run command with some failures."""
        # Setup mocks
        mock_ctx = Mock()
        mock_ctx.project_path = Path(mock_args.project_folder)
        mock_ctx.vars = {}
        mock_ctx.select_patterns = None
        mock_ctx.exclude_patterns = None
        mock_ctx.config = {"connection": {"type": "duckdb", "path": ":memory:"}}
        mock_ctx.print_variables_info = Mock()
        mock_ctx.print_selection_info = Mock()
        mock_context_class.return_value = mock_ctx

        mock_connection_manager = Mock()
        mock_connection_manager_class.return_value = mock_connection_manager

        # Mock execution with failures
        mock_execute_models.return_value = {
            "executed_tables": ["schema1.table1"],
            "failed_tables": [{"table": "schema1.table2", "error": "SQL error"}],
            "warnings": [],
        }

        # Capture stdout
        with patch("sys.stdout", new=StringIO()) as fake_out:
            cmd_run(mock_args)

        output = fake_out.getvalue()
        # New format includes emoji and proper pluralization: "✅ Successful: 1 table, 0 functions"
        assert "Successful: 1 table" in output or "✅ Successful: 1 table" in output
        assert "Failed: 1 table" in output or "❌ Failed: 1 table" in output

    @patch("tee.cli.commands.run.execute_models")
    @patch("tee.cli.commands.run.ConnectionManager")
    @patch("tee.cli.commands.run.CommandContext")
    def test_cmd_run_with_warnings(
        self, mock_context_class, mock_connection_manager_class, mock_execute_models, mock_args
    ):
        """Test run command with warnings."""
        # Setup mocks
        mock_ctx = Mock()
        mock_ctx.project_path = Path(mock_args.project_folder)
        mock_ctx.vars = {}
        mock_ctx.select_patterns = None
        mock_ctx.exclude_patterns = None
        mock_ctx.config = {"connection": {"type": "duckdb", "path": ":memory:"}}
        mock_ctx.print_variables_info = Mock()
        mock_ctx.print_selection_info = Mock()
        mock_context_class.return_value = mock_ctx

        mock_connection_manager = Mock()
        mock_connection_manager_class.return_value = mock_connection_manager

        # Mock execution with warnings
        mock_execute_models.return_value = {
            "executed_tables": ["schema1.table1"],
            "failed_tables": [],
            "warnings": ["Warning: Table schema1.table1 has no primary key"],
        }

        # Capture stdout
        with patch("sys.stdout", new=StringIO()) as fake_out:
            cmd_run(mock_args)

        output = fake_out.getvalue()
        # New format includes emoji and proper pluralization: "⚠️  Warnings: 1 warning"
        assert "Warnings: 1 warning" in output or "⚠️  Warnings: 1 warning" in output

    @patch("tee.cli.commands.run.execute_models")
    @patch("tee.cli.commands.run.ConnectionManager")
    @patch("tee.cli.commands.run.CommandContext")
    def test_cmd_run_verbose_mode(
        self, mock_context_class, mock_connection_manager_class, mock_execute_models, mock_args
    ):
        """Test run command with verbose output."""
        # Setup mocks
        mock_ctx = Mock()
        mock_ctx.project_path = Path(mock_args.project_folder)
        mock_ctx.vars = {}
        mock_ctx.select_patterns = None
        mock_ctx.exclude_patterns = None
        mock_ctx.config = {"connection": {"type": "duckdb", "path": ":memory:"}}
        mock_ctx.verbose = True
        mock_ctx.print_variables_info = Mock()
        mock_ctx.print_selection_info = Mock()
        mock_context_class.return_value = mock_ctx

        mock_connection_manager = Mock()
        mock_connection_manager_class.return_value = mock_connection_manager

        # Mock execution results with analysis
        mock_execute_models.return_value = {
            "executed_tables": ["schema1.table1"],
            "failed_tables": [],
            "warnings": [],
            "analysis": {"total_models": 1, "execution_time": 1.5},
        }

        # Capture stdout
        with patch("sys.stdout", new=StringIO()) as fake_out:
            cmd_run(mock_args)

        output = fake_out.getvalue()
        assert "Analysis info:" in output

    @patch("tee.cli.commands.run.execute_models")
    @patch("tee.cli.commands.run.ConnectionManager")
    @patch("tee.cli.commands.run.CommandContext")
    def test_cmd_run_with_variables(
        self, mock_context_class, mock_connection_manager_class, mock_execute_models, mock_args
    ):
        """Test run command with variables."""
        # Setup mocks
        mock_ctx = Mock()
        mock_ctx.project_path = Path(mock_args.project_folder)
        mock_ctx.vars = {"env": "production", "debug": "true"}
        mock_ctx.select_patterns = None
        mock_ctx.exclude_patterns = None
        mock_ctx.config = {"connection": {"type": "duckdb", "path": ":memory:"}}
        mock_ctx.print_variables_info = Mock()
        mock_ctx.print_selection_info = Mock()
        mock_context_class.return_value = mock_ctx

        mock_connection_manager = Mock()
        mock_connection_manager_class.return_value = mock_connection_manager

        # Mock successful execution
        mock_execute_models.return_value = {
            "executed_tables": ["schema1.table1"],
            "failed_tables": [],
            "warnings": [],
        }

        # Capture stdout
        with patch("sys.stdout", new=StringIO()):
            cmd_run(mock_args)

        # Verify variables were passed
        call_args = mock_execute_models.call_args
        assert call_args.kwargs["variables"] == {"env": "production", "debug": "true"}

    @patch("tee.cli.commands.run.execute_models")
    @patch("tee.cli.commands.run.ConnectionManager")
    @patch("tee.cli.commands.run.CommandContext")
    def test_cmd_run_with_selection_patterns(
        self, mock_context_class, mock_connection_manager_class, mock_execute_models, mock_args
    ):
        """Test run command with select/exclude patterns."""
        # Setup mocks
        mock_ctx = Mock()
        mock_ctx.project_path = Path(mock_args.project_folder)
        mock_ctx.vars = {}
        mock_ctx.select_patterns = ["schema1.*"]
        mock_ctx.exclude_patterns = ["*.temp"]
        mock_ctx.config = {"connection": {"type": "duckdb", "path": ":memory:"}}
        mock_ctx.print_variables_info = Mock()
        mock_ctx.print_selection_info = Mock()
        mock_context_class.return_value = mock_ctx

        mock_connection_manager = Mock()
        mock_connection_manager_class.return_value = mock_connection_manager

        # Mock successful execution
        mock_execute_models.return_value = {
            "executed_tables": ["schema1.table1"],
            "failed_tables": [],
            "warnings": [],
        }

        # Capture stdout
        with patch("sys.stdout", new=StringIO()):
            cmd_run(mock_args)

        # Verify selection patterns were passed
        call_args = mock_execute_models.call_args
        assert call_args.kwargs["select_patterns"] == ["schema1.*"]
        assert call_args.kwargs["exclude_patterns"] == ["*.temp"]

    @patch("tee.cli.commands.run.execute_models")
    @patch("tee.cli.commands.run.ConnectionManager")
    @patch("tee.cli.commands.run.CommandContext")
    def test_cmd_run_handles_exceptions(
        self, mock_context_class, mock_connection_manager_class, mock_execute_models, mock_args
    ):
        """Test run command handles exceptions gracefully."""
        # Setup mocks
        mock_ctx = Mock()
        mock_ctx.project_path = Path(mock_args.project_folder)
        mock_ctx.vars = {}
        mock_ctx.config = {"connection": {"type": "duckdb", "path": ":memory:"}}
        mock_ctx.print_variables_info = Mock()
        mock_ctx.print_selection_info = Mock()
        mock_ctx.handle_error = Mock()
        mock_context_class.return_value = mock_ctx

        mock_connection_manager = Mock()
        mock_connection_manager_class.return_value = mock_connection_manager

        # Mock exception
        mock_execute_models.side_effect = Exception("Database connection failed")

        # Capture stdout
        with patch("sys.stdout", new=StringIO()):
            cmd_run(mock_args)

        # Verify error was handled
        mock_ctx.handle_error.assert_called_once()

    @patch("tee.cli.commands.run.execute_models")
    @patch("tee.cli.commands.run.ConnectionManager")
    @patch("tee.cli.commands.run.CommandContext")
    def test_cmd_run_cleanup_connection_manager(
        self, mock_context_class, mock_connection_manager_class, mock_execute_models, mock_args
    ):
        """Test that connection manager is cleaned up."""
        # Setup mocks
        mock_ctx = Mock()
        mock_ctx.project_path = Path(mock_args.project_folder)
        mock_ctx.vars = {}
        mock_ctx.select_patterns = None
        mock_ctx.exclude_patterns = None
        mock_ctx.config = {"connection": {"type": "duckdb", "path": ":memory:"}}
        mock_ctx.print_variables_info = Mock()
        mock_ctx.print_selection_info = Mock()
        mock_context_class.return_value = mock_ctx

        mock_connection_manager = Mock()
        mock_connection_manager_class.return_value = mock_connection_manager

        # Mock successful execution
        mock_execute_models.return_value = {
            "executed_tables": ["schema1.table1"],
            "failed_tables": [],
            "warnings": [],
        }

        # Capture stdout
        with patch("sys.stdout", new=StringIO()):
            cmd_run(mock_args)

        # Verify cleanup was called
        mock_connection_manager.cleanup.assert_called_once()

    @patch("tee.cli.commands.run.execute_models")
    @patch("tee.cli.commands.run.ConnectionManager")
    @patch("tee.cli.commands.run.CommandContext")
    def test_cmd_run_cleanup_on_exception(
        self, mock_context_class, mock_connection_manager_class, mock_execute_models, mock_args
    ):
        """Test that connection manager is cleaned up even on exception."""
        # Setup mocks
        mock_ctx = Mock()
        mock_ctx.project_path = Path(mock_args.project_folder)
        mock_ctx.vars = {}
        mock_ctx.config = {"connection": {"type": "duckdb", "path": ":memory:"}}
        mock_ctx.print_variables_info = Mock()
        mock_ctx.print_selection_info = Mock()
        mock_ctx.handle_error = Mock()
        mock_context_class.return_value = mock_ctx

        mock_connection_manager = Mock()
        mock_connection_manager_class.return_value = mock_connection_manager

        # Mock exception
        mock_execute_models.side_effect = Exception("Database connection failed")

        # Capture stdout
        with patch("sys.stdout", new=StringIO()):
            cmd_run(mock_args)

        # Verify cleanup was still called
        mock_connection_manager.cleanup.assert_called_once()
