"""
Tests for the debug CLI command.
"""

import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from tee.cli.commands.debug import cmd_debug


class TestDebugCommand:
    """Tests for the debug CLI command."""

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
        return args

    @patch("tee.cli.commands.debug.ConnectionManager")
    @patch("tee.cli.commands.debug.CommandContext")
    def test_cmd_debug_success(self, mock_context_class, mock_connection_manager_class, mock_args):
        """Test successful debug command execution."""
        # Setup mocks
        mock_ctx = Mock()
        mock_ctx.project_path = Path(mock_args.project_folder)
        mock_ctx.vars = {}
        mock_ctx.config = {"connection": {"type": "duckdb", "path": ":memory:"}}
        mock_ctx.print_variables_info = Mock()
        mock_context_class.return_value = mock_ctx

        # Mock connection manager
        mock_connection_manager = Mock()
        mock_connection_manager.test_connection.return_value = True
        mock_connection_manager.get_database_info.return_value = {
            "database_type": "DuckDB",
            "adapter_type": "duckdb",
            "version": "1.0.0",
        }
        mock_connection_manager.get_supported_materializations.return_value = ["table", "view"]
        mock_connection_manager_class.return_value = mock_connection_manager

        # Capture stdout
        with patch("sys.stdout", new=StringIO()) as fake_out:
            cmd_debug(mock_args)

        output = fake_out.getvalue()
        assert "Testing database connectivity" in output
        assert "DATABASE CONNECTION TEST" in output
        assert "Database connection successful!" in output
        assert "Database Information:" in output
        assert "database_type: DuckDB" in output
        assert "Supported Materializations:" in output
        assert "All connectivity tests passed!" in output

        # Verify connection manager was used correctly
        mock_connection_manager.test_connection.assert_called_once()
        mock_connection_manager.get_database_info.assert_called_once()
        mock_connection_manager.get_supported_materializations.assert_called_once()

    @patch("tee.cli.commands.debug.ConnectionManager")
    @patch("tee.cli.commands.debug.CommandContext")
    def test_cmd_debug_connection_failure(
        self, mock_context_class, mock_connection_manager_class, mock_args
    ):
        """Test debug command when connection fails."""
        # Setup mocks
        mock_ctx = Mock()
        mock_ctx.project_path = Path(mock_args.project_folder)
        mock_ctx.vars = {}
        mock_ctx.config = {"connection": {"type": "duckdb", "path": ":memory:"}}
        mock_ctx.print_variables_info = Mock()
        mock_context_class.return_value = mock_ctx

        # Mock connection manager with failed connection
        mock_connection_manager = Mock()
        mock_connection_manager.test_connection.return_value = False
        mock_connection_manager_class.return_value = mock_connection_manager

        # Capture both stdout and stderr (typer.echo with err=True writes to stderr)
        with (
            patch("sys.stdout", new=StringIO()) as fake_out,
            patch("sys.stderr", new=StringIO()) as fake_err,
        ):
            cmd_debug(mock_args)

        output = fake_out.getvalue() + fake_err.getvalue()
        assert "Database connection failed!" in output
        assert "Please check your connection configuration" in output

    @patch("tee.cli.commands.debug.ConnectionManager")
    @patch("tee.cli.commands.debug.CommandContext")
    def test_cmd_debug_with_database_info(
        self, mock_context_class, mock_connection_manager_class, mock_args
    ):
        """Test debug command with full database info."""
        # Setup mocks
        mock_ctx = Mock()
        mock_ctx.project_path = Path(mock_args.project_folder)
        mock_ctx.vars = {}
        mock_ctx.config = {
            "connection": {"type": "snowflake", "host": "account.snowflakecomputing.com"}
        }
        mock_ctx.print_variables_info = Mock()
        mock_context_class.return_value = mock_ctx

        # Mock connection manager with Snowflake info
        mock_connection_manager = Mock()
        mock_connection_manager.test_connection.return_value = True
        mock_connection_manager.get_database_info.return_value = {
            "database_type": "Snowflake",
            "adapter_type": "snowflake",
            "host": "account.snowflakecomputing.com",
            "database": "MY_DB",
            "warehouse": "MY_WAREHOUSE",
            "role": "MY_ROLE",
        }
        mock_connection_manager.get_supported_materializations.return_value = [
            "table",
            "view",
            "incremental",
        ]
        mock_connection_manager_class.return_value = mock_connection_manager

        # Capture stdout
        with patch("sys.stdout", new=StringIO()) as fake_out:
            cmd_debug(mock_args)

        output = fake_out.getvalue()
        assert "host: account.snowflakecomputing.com" in output
        assert "database: MY_DB" in output
        assert "warehouse: MY_WAREHOUSE" in output
        assert "role: MY_ROLE" in output

    @patch("tee.cli.commands.debug.ConnectionManager")
    @patch("tee.cli.commands.debug.CommandContext")
    def test_cmd_debug_handles_exceptions(
        self, mock_context_class, mock_connection_manager_class, mock_args
    ):
        """Test debug command handles exceptions gracefully."""
        # Setup mocks
        mock_ctx = Mock()
        mock_ctx.project_path = Path(mock_args.project_folder)
        mock_ctx.vars = {}
        mock_ctx.config = {"connection": {"type": "duckdb", "path": ":memory:"}}
        mock_ctx.print_variables_info = Mock()
        mock_ctx.handle_error = Mock()
        mock_context_class.return_value = mock_ctx

        # Mock connection manager that raises exception
        mock_connection_manager = Mock()
        mock_connection_manager.test_connection.side_effect = Exception("Connection error")
        mock_connection_manager_class.return_value = mock_connection_manager

        # Capture stdout
        with patch("sys.stdout", new=StringIO()):
            cmd_debug(mock_args)

        # Verify error was handled
        mock_ctx.handle_error.assert_called_once()

    @patch("tee.cli.commands.debug.ConnectionManager")
    @patch("tee.cli.commands.debug.CommandContext")
    def test_cmd_debug_cleanup_connection_manager(
        self, mock_context_class, mock_connection_manager_class, mock_args
    ):
        """Test that connection manager is cleaned up."""
        # Setup mocks
        mock_ctx = Mock()
        mock_ctx.project_path = Path(mock_args.project_folder)
        mock_ctx.vars = {}
        mock_ctx.config = {"connection": {"type": "duckdb", "path": ":memory:"}}
        mock_ctx.print_variables_info = Mock()
        mock_context_class.return_value = mock_ctx

        # Mock connection manager
        mock_connection_manager = Mock()
        mock_connection_manager.test_connection.return_value = True
        mock_connection_manager.get_database_info.return_value = {}
        mock_connection_manager.get_supported_materializations.return_value = []
        mock_connection_manager_class.return_value = mock_connection_manager

        # Capture stdout
        with patch("sys.stdout", new=StringIO()):
            cmd_debug(mock_args)

        # Verify cleanup was called
        mock_connection_manager.cleanup.assert_called_once()

    @patch("tee.cli.commands.debug.ConnectionManager")
    @patch("tee.cli.commands.debug.CommandContext")
    def test_cmd_debug_cleanup_on_exception(
        self, mock_context_class, mock_connection_manager_class, mock_args
    ):
        """Test that connection manager is cleaned up even on exception."""
        # Setup mocks
        mock_ctx = Mock()
        mock_ctx.project_path = Path(mock_args.project_folder)
        mock_ctx.vars = {}
        mock_ctx.config = {"connection": {"type": "duckdb", "path": ":memory:"}}
        mock_ctx.print_variables_info = Mock()
        mock_ctx.handle_error = Mock()
        mock_context_class.return_value = mock_ctx

        # Mock connection manager that raises exception
        mock_connection_manager = Mock()
        mock_connection_manager.test_connection.side_effect = Exception("Connection error")
        mock_connection_manager_class.return_value = mock_connection_manager

        # Capture stdout
        with patch("sys.stdout", new=StringIO()):
            cmd_debug(mock_args)

        # Verify cleanup was still called
        mock_connection_manager.cleanup.assert_called_once()

    @patch("tee.cli.commands.debug.ConnectionManager")
    @patch("tee.cli.commands.debug.CommandContext")
    def test_cmd_debug_with_variables(
        self, mock_context_class, mock_connection_manager_class, mock_args
    ):
        """Test debug command with variables."""
        # Setup mocks
        mock_ctx = Mock()
        mock_ctx.project_path = Path(mock_args.project_folder)
        mock_ctx.vars = {"env": "production"}
        mock_ctx.config = {"connection": {"type": "duckdb", "path": ":memory:"}}
        mock_ctx.print_variables_info = Mock()
        mock_context_class.return_value = mock_ctx

        # Mock connection manager
        mock_connection_manager = Mock()
        mock_connection_manager.test_connection.return_value = True
        mock_connection_manager.get_database_info.return_value = {}
        mock_connection_manager.get_supported_materializations.return_value = []
        mock_connection_manager_class.return_value = mock_connection_manager

        # Capture stdout
        with patch("sys.stdout", new=StringIO()):
            cmd_debug(mock_args)

        # Verify variables were passed to ConnectionManager
        call_args = mock_connection_manager_class.call_args
        assert call_args.kwargs["variables"] == {"env": "production"}
