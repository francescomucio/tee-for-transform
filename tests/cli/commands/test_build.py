"""
Unit tests for build command.
"""

import contextlib
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from click.exceptions import Exit as ClickExit

from t4t.cli.commands.build import cmd_build


class TestBuildCommand:
    """Test cases for build command."""

    @pytest.fixture(autouse=True)
    def mock_lookup_generation(self):
        """Prevent lookup generator side effects in unit tests."""
        with patch("t4t.cli.commands.build.generate_lookups"):
            yield

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def mock_args(self, temp_dir):
        """Create mock CLI arguments."""
        args = Mock()
        args.project_folder = str(temp_dir)
        args.variables = {}
        args.select = None
        args.exclude = None
        args.verbose = False
        return args

    @pytest.fixture
    def mock_config(self):
        """Create mock project configuration."""
        return {
            "connection": {
                "type": "duckdb",
                "database": ":memory:",
            }
        }

    @patch("t4t.cli.commands.build.build_models")
    @patch("t4t.cli.commands.build.ConnectionManager")
    @patch("t4t.cli.commands.build.CommandContext")
    def test_build_success(
        self,
        mock_context_class,
        mock_connection_manager_class,
        mock_build_models,
        mock_args,
        mock_config,
    ):
        """Test successful build with all tests passing."""
        # Setup mocks
        mock_ctx = Mock()
        mock_ctx.project_path = Path(mock_args.project_folder)
        mock_ctx.vars = {}
        mock_ctx.select_patterns = None
        mock_ctx.exclude_patterns = None
        mock_ctx.config = mock_config
        mock_ctx.print_variables_info = Mock()
        mock_ctx.print_selection_info = Mock()
        mock_context_class.return_value = mock_ctx

        mock_connection_manager = Mock()
        mock_connection_manager_class.return_value = mock_connection_manager

        # Mock successful build results
        mock_build_models.return_value = {
            "executed_tables": ["schema1.table1", "schema1.table2"],
            "failed_tables": [],
            "test_results": {
                "total": 4,
                "passed": 4,
                "failed": 0,
                "warnings": 0,
            },
        }

        # Capture stdout
        with patch("sys.stdout", new=StringIO()) as fake_out:
            try:
                cmd_build(mock_args)
            except SystemExit as e:
                # Should exit with 0 on success
                # typer.Exit uses .exit_code, SystemExit uses .code
                exit_code = getattr(e, "exit_code", getattr(e, "code", 0))
                assert exit_code == 0

        output = fake_out.getvalue()
        assert "Building project:" in output
        assert "Completed!" in output
        assert "All 2 tables executed successfully!" in output
        assert "All 4 tests passed!" in output

        # Verify build_models was called correctly
        mock_build_models.assert_called_once_with(
            project_folder=str(mock_ctx.project_path),
            connection_config=mock_config["connection"],
            save_analysis=True,
            variables={},
            select_patterns=None,
            exclude_patterns=None,
            project_config=mock_ctx.config,
        )

    @patch("t4t.cli.commands.build.build_models")
    @patch("t4t.cli.commands.build.ConnectionManager")
    @patch("t4t.cli.commands.build.CommandContext")
    def test_build_with_test_failures(
        self,
        mock_context_class,
        mock_connection_manager_class,
        mock_build_models,
        mock_args,
        mock_config,
    ):
        """Test build that fails due to test failures."""
        # Setup mocks
        mock_ctx = Mock()
        mock_ctx.project_path = Path(mock_args.project_folder)
        mock_ctx.vars = {}
        mock_ctx.select_patterns = None
        mock_ctx.exclude_patterns = None
        mock_ctx.config = mock_config
        mock_ctx.print_variables_info = Mock()
        mock_ctx.print_selection_info = Mock()
        mock_context_class.return_value = mock_ctx

        mock_connection_manager = Mock()
        mock_connection_manager_class.return_value = mock_connection_manager

        # Mock build results with test failures
        mock_build_models.return_value = {
            "executed_tables": ["schema1.table1"],
            "failed_tables": [],
            "test_results": {
                "total": 3,
                "passed": 2,
                "failed": 1,
                "warnings": 0,
            },
        }

        # Capture stdout
        with patch("sys.stdout", new=StringIO()) as fake_out:
            try:
                cmd_build(mock_args)
            except SystemExit as e:
                # Should exit with 1 on failure
                exit_code = getattr(e, "exit_code", getattr(e, "code", 0))
                assert exit_code == 1

        output = fake_out.getvalue()
        assert "Failed tests: 1" in output

    @patch("t4t.cli.commands.build.build_models")
    @patch("t4t.cli.commands.build.ConnectionManager")
    @patch("t4t.cli.commands.build.CommandContext")
    def test_build_with_model_failures(
        self,
        mock_context_class,
        mock_connection_manager_class,
        mock_build_models,
        mock_args,
        mock_config,
    ):
        """Test build that fails due to model execution failures."""
        # Setup mocks
        mock_ctx = Mock()
        mock_ctx.project_path = Path(mock_args.project_folder)
        mock_ctx.vars = {}
        mock_ctx.select_patterns = None
        mock_ctx.exclude_patterns = None
        mock_ctx.config = mock_config
        mock_ctx.print_variables_info = Mock()
        mock_ctx.print_selection_info = Mock()
        mock_context_class.return_value = mock_ctx

        mock_connection_manager = Mock()
        mock_connection_manager_class.return_value = mock_connection_manager

        # Mock build results with model failures
        mock_build_models.return_value = {
            "executed_tables": ["schema1.table1"],
            "failed_tables": [{"table": "schema1.table2", "error": "SQL error"}],
            "test_results": {
                "total": 2,
                "passed": 2,
                "failed": 0,
                "warnings": 0,
            },
        }

        # Capture stdout
        with patch("sys.stdout", new=StringIO()) as fake_out:
            try:
                cmd_build(mock_args)
            except SystemExit as e:
                # Should exit with 1 on failure
                exit_code = getattr(e, "exit_code", getattr(e, "code", 0))
                assert exit_code == 1

        output = fake_out.getvalue()
        assert "Failed models: 1" in output

    @patch("t4t.cli.commands.build.build_models")
    @patch("t4t.cli.commands.build.ConnectionManager")
    @patch("t4t.cli.commands.build.CommandContext")
    def test_build_with_warnings(
        self,
        mock_context_class,
        mock_connection_manager_class,
        mock_build_models,
        mock_args,
        mock_config,
    ):
        """Test build with test warnings (should still succeed)."""
        # Setup mocks
        mock_ctx = Mock()
        mock_ctx.project_path = Path(mock_args.project_folder)
        mock_ctx.vars = {}
        mock_ctx.select_patterns = None
        mock_ctx.exclude_patterns = None
        mock_ctx.config = mock_config
        mock_ctx.print_variables_info = Mock()
        mock_ctx.print_selection_info = Mock()
        mock_context_class.return_value = mock_ctx

        mock_connection_manager = Mock()
        mock_connection_manager_class.return_value = mock_connection_manager

        # Mock build results with warnings
        mock_build_models.return_value = {
            "executed_tables": ["schema1.table1"],
            "failed_tables": [],
            "test_results": {
                "total": 3,
                "passed": 2,
                "failed": 0,
                "warnings": 1,
            },
        }

        # Capture stdout
        with patch("sys.stdout", new=StringIO()) as fake_out:
            try:
                cmd_build(mock_args)
            except SystemExit as e:
                # Should exit with 0 (warnings don't fail the build)
                exit_code = getattr(e, "exit_code", getattr(e, "code", 0))
                assert exit_code == 0

        output = fake_out.getvalue()
        # New format uses pluralize: "All 1 table executed successfully!" (singular)
        assert (
            "All 1 table executed successfully!" in output
            or "All 1 tables executed successfully!" in output
        )

    @patch("t4t.cli.commands.build.build_models")
    @patch("t4t.cli.commands.build.ConnectionManager")
    @patch("t4t.cli.commands.build.CommandContext")
    def test_build_handles_keyboard_interrupt(
        self,
        mock_context_class,
        mock_connection_manager_class,
        mock_build_models,
        mock_args,
        mock_config,
    ):
        """Test that KeyboardInterrupt is handled gracefully."""
        # Setup mocks
        mock_ctx = Mock()
        mock_ctx.project_path = Path(mock_args.project_folder)
        mock_ctx.vars = {}
        mock_ctx.config = mock_config
        mock_ctx.print_variables_info = Mock()
        mock_ctx.print_selection_info = Mock()
        mock_context_class.return_value = mock_ctx

        mock_connection_manager = Mock()
        mock_connection_manager_class.return_value = mock_connection_manager

        # Mock KeyboardInterrupt
        mock_build_models.side_effect = KeyboardInterrupt()

        # Capture stdout
        with patch("sys.stdout", new=StringIO()) as fake_out:
            try:
                cmd_build(mock_args)
            except (SystemExit, ClickExit) as e:
                # Should exit with 130 for KeyboardInterrupt
                # typer.Exit raises click.exceptions.Exit which is a SystemExit subclass
                # click.exceptions.Exit uses .exit_code attribute
                exit_code = getattr(e, "exit_code", getattr(e, "code", 0))
                assert exit_code == 130, f"Expected exit code 130, got {exit_code}"

        output = fake_out.getvalue()
        assert "Build interrupted by user" in output

    @patch("t4t.cli.commands.build.build_models")
    @patch("t4t.cli.commands.build.ConnectionManager")
    @patch("t4t.cli.commands.build.CommandContext")
    def test_build_handles_exceptions(
        self,
        mock_context_class,
        mock_connection_manager_class,
        mock_build_models,
        mock_args,
        mock_config,
    ):
        """Test that exceptions are handled and reported."""
        # Setup mocks
        mock_ctx = Mock()
        mock_ctx.project_path = Path(mock_args.project_folder)
        mock_ctx.vars = {}
        mock_ctx.config = mock_config
        mock_ctx.print_variables_info = Mock()
        mock_ctx.print_selection_info = Mock()
        mock_ctx.handle_error = Mock()
        mock_context_class.return_value = mock_ctx

        mock_connection_manager = Mock()
        mock_connection_manager_class.return_value = mock_connection_manager

        # Mock exception
        mock_build_models.side_effect = Exception("Database connection failed")

        # Capture stdout
        with patch("sys.stdout", new=StringIO()):
            try:
                cmd_build(mock_args)
            except SystemExit as e:
                # Should exit with 1 on error
                assert e.code == 1

        # Verify error was handled
        mock_ctx.handle_error.assert_called_once()

    @patch("t4t.cli.commands.build.build_models")
    @patch("t4t.cli.commands.build.ConnectionManager")
    @patch("t4t.cli.commands.build.CommandContext")
    def test_build_cleanup_connection_manager(
        self,
        mock_context_class,
        mock_connection_manager_class,
        mock_build_models,
        mock_args,
        mock_config,
    ):
        """Test that connection manager is cleaned up."""
        # Setup mocks
        mock_ctx = Mock()
        mock_ctx.project_path = Path(mock_args.project_folder)
        mock_ctx.vars = {}
        mock_ctx.config = mock_config
        mock_ctx.print_variables_info = Mock()
        mock_ctx.print_selection_info = Mock()
        mock_context_class.return_value = mock_ctx

        mock_connection_manager = Mock()
        mock_connection_manager_class.return_value = mock_connection_manager

        # Mock successful build
        mock_build_models.return_value = {
            "executed_tables": ["schema1.table1"],
            "failed_tables": [],
            "test_results": {
                "total": 1,
                "passed": 1,
                "failed": 0,
                "warnings": 0,
            },
        }

        # Capture stdout
        with patch("sys.stdout", new=StringIO()), contextlib.suppress(SystemExit):
            cmd_build(mock_args)

        # Verify cleanup was called
        mock_connection_manager.cleanup.assert_called_once()

    @patch("t4t.cli.commands.build.build_models")
    @patch("t4t.cli.commands.build.ConnectionManager")
    @patch("t4t.cli.commands.build.CommandContext")
    def test_build_with_variables(
        self,
        mock_context_class,
        mock_connection_manager_class,
        mock_build_models,
        mock_args,
        mock_config,
    ):
        """Test build with variables passed through."""
        # Setup mocks
        mock_ctx = Mock()
        mock_ctx.project_path = Path(mock_args.project_folder)
        mock_ctx.vars = {"env": "production", "debug": "true"}
        mock_ctx.select_patterns = None
        mock_ctx.exclude_patterns = None
        mock_ctx.config = mock_config
        mock_ctx.print_variables_info = Mock()
        mock_ctx.print_selection_info = Mock()
        mock_context_class.return_value = mock_ctx

        mock_connection_manager = Mock()
        mock_connection_manager_class.return_value = mock_connection_manager

        # Mock successful build
        mock_build_models.return_value = {
            "executed_tables": ["schema1.table1"],
            "failed_tables": [],
            "test_results": {
                "total": 1,
                "passed": 1,
                "failed": 0,
                "warnings": 0,
            },
        }

        # Capture stdout
        with patch("sys.stdout", new=StringIO()), contextlib.suppress(SystemExit):
            cmd_build(mock_args)

        # Verify variables were passed to build_models
        call_args = mock_build_models.call_args
        assert call_args.kwargs["variables"] == {"env": "production", "debug": "true"}

    @patch("t4t.cli.commands.build.build_models")
    @patch("t4t.cli.commands.build.ConnectionManager")
    @patch("t4t.cli.commands.build.CommandContext")
    def test_build_with_selection_patterns(
        self,
        mock_context_class,
        mock_connection_manager_class,
        mock_build_models,
        mock_args,
        mock_config,
    ):
        """Test build with select/exclude patterns."""
        # Setup mocks
        mock_ctx = Mock()
        mock_ctx.project_path = Path(mock_args.project_folder)
        mock_ctx.vars = {}
        mock_ctx.select_patterns = ["schema1.*"]
        mock_ctx.exclude_patterns = ["*.temp"]
        mock_ctx.config = mock_config
        mock_ctx.print_variables_info = Mock()
        mock_ctx.print_selection_info = Mock()
        mock_context_class.return_value = mock_ctx

        mock_connection_manager = Mock()
        mock_connection_manager_class.return_value = mock_connection_manager

        # Mock successful build
        mock_build_models.return_value = {
            "executed_tables": ["schema1.table1"],
            "failed_tables": [],
            "test_results": {
                "total": 1,
                "passed": 1,
                "failed": 0,
                "warnings": 0,
            },
        }

        # Capture stdout
        with patch("sys.stdout", new=StringIO()), contextlib.suppress(SystemExit):
            cmd_build(mock_args)

        # Verify selection patterns were passed
        call_args = mock_build_models.call_args
        assert call_args.kwargs["select_patterns"] == ["schema1.*"]
        assert call_args.kwargs["exclude_patterns"] == ["*.temp"]
