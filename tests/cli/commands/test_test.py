"""
Tests for the test CLI command.
"""

import contextlib
import tempfile
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest
import typer

from t4t.cli.commands.test import cmd_test


class TestTestCommand:
    """Tests for the test CLI command."""

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
        args.severity = None
        return args

    def _setup_real_project(
        self, temp_dir: Path, models_sql: dict[str, str], connection_config: dict[str, Any]
    ) -> Path:
        """Helper to set up a real project structure with models and compile to OTS."""
        # Create project structure
        models_dir = temp_dir / "models"
        models_dir.mkdir(parents=True, exist_ok=True)

        # Create project.toml
        project_toml = temp_dir / "project.toml"
        path_config = (
            f'path = "{connection_config.get("path", ":memory:")}"'
            if "path" in connection_config
            else ""
        )
        project_toml.write_text(
            f'name = "test_project"\n[connection]\ntype = "{connection_config["type"]}"\n{path_config}\n'
        )

        # Create SQL model files
        for table_name, sql in models_sql.items():
            # Extract schema and table from table_name (format: schema.table)
            if "." in table_name:
                schema, table = table_name.split(".", 1)
                schema_dir = models_dir / schema
                schema_dir.mkdir(exist_ok=True)
                model_file = schema_dir / f"{table}.sql"
            else:
                model_file = models_dir / f"{table_name}.sql"
            model_file.write_text(sql)

        # Actually compile the project to create real OTS modules
        from t4t.compiler import compile_project

        compile_project(
            project_folder=str(temp_dir),
            connection_config=connection_config,
            variables={},
            project_config={"name": "test_project", "connection": connection_config},
        )

        return temp_dir

    @patch("t4t.cli.commands.test.TestExecutor")
    @patch("t4t.cli.commands.test.ExecutionEngine")
    @patch("t4t.cli.commands.test.ProjectParser")
    @patch("t4t.cli.commands.test.CommandContext")
    def test_cmd_test_success(
        self,
        mock_context_class,
        mock_parser_class,
        mock_engine_class,
        mock_executor_class,
        mock_args,
    ):
        """Test successful test command execution with real compilation."""
        # Set up real project with SQL models
        models_sql = {
            "schema1.table1": "SELECT 1 as id, 'test' as name",
        }
        connection_config = {"type": "duckdb", "path": ":memory:"}
        project_path = self._setup_real_project(
            Path(mock_args.project_folder), models_sql, connection_config
        )

        # Setup mocks
        mock_ctx = Mock()
        mock_ctx.project_path = project_path
        mock_ctx.vars = {}
        mock_ctx.select_patterns = None
        mock_ctx.exclude_patterns = None
        mock_ctx.config = {"connection": connection_config}
        mock_ctx.print_variables_info = Mock()
        mock_ctx.print_selection_info = Mock()
        mock_context_class.return_value = mock_ctx

        # Mock parser (for dependency graph building - real OTS modules will be loaded)
        mock_parser = Mock()
        mock_parser.build_dependency_graph.return_value = {"nodes": ["schema1.table1"]}
        mock_parser.get_execution_order.return_value = ["schema1.table1"]
        mock_parser_class.return_value = mock_parser

        # Mock execution engine
        mock_engine = Mock()
        mock_adapter = Mock()
        mock_adapter.config.type = "duckdb"
        mock_engine.adapter = mock_adapter
        mock_engine_class.return_value = mock_engine

        # Mock test executor
        mock_executor = Mock()
        mock_executor.execute_all_tests.return_value = {
            "total": 2,
            "passed": 2,
            "failed": 0,
            "warnings": [],
            "errors": [],
            "test_results": [],
        }
        mock_executor_class.return_value = mock_executor

        # Capture stdout
        with (
            patch("sys.stdout", new=StringIO()) as fake_out,
            contextlib.suppress(SystemExit),  # may exit with 0
        ):
            cmd_test(mock_args)

        output = fake_out.getvalue()
        assert "Running tests for project:" in output
        assert "EXECUTING TESTS" in output
        assert "Test Results:" in output
        assert "Total tests: 2" in output
        assert "Passed: 2" in output
        assert "Failed: 0" in output
        assert "All tests passed!" in output

    @patch("t4t.cli.commands.test.TestExecutor")
    @patch("t4t.cli.commands.test.ExecutionEngine")
    @patch("t4t.cli.commands.test.ProjectParser")
    @patch("t4t.cli.commands.test.CommandContext")
    def test_cmd_test_with_failures(
        self,
        mock_context_class,
        mock_parser_class,
        mock_engine_class,
        mock_executor_class,
        mock_args,
    ):
        """Test test command with test failures."""
        # Set up real project with SQL models
        models_sql = {
            "schema1.table1": "SELECT 1 as id, 'test' as name",
        }
        connection_config = {"type": "duckdb", "path": ":memory:"}
        project_path = self._setup_real_project(
            Path(mock_args.project_folder), models_sql, connection_config
        )

        # Setup mocks
        mock_ctx = Mock()
        mock_ctx.project_path = project_path
        mock_ctx.vars = {}
        mock_ctx.select_patterns = None
        mock_ctx.exclude_patterns = None
        mock_ctx.config = {"connection": connection_config}
        mock_ctx.print_variables_info = Mock()
        mock_ctx.print_selection_info = Mock()
        mock_context_class.return_value = mock_ctx

        # Mock parser (for dependency graph building - real OTS modules will be loaded)
        mock_parser = Mock()
        mock_parser.build_dependency_graph.return_value = {"nodes": ["schema1.table1"]}
        mock_parser.get_execution_order.return_value = ["schema1.table1"]
        mock_parser_class.return_value = mock_parser

        # Mock execution engine
        mock_engine = Mock()
        mock_adapter = Mock()
        mock_adapter.config.type = "duckdb"
        mock_engine.adapter = mock_adapter
        mock_engine_class.return_value = mock_engine

        # Mock test executor with failures
        mock_executor = Mock()
        mock_executor.execute_all_tests.return_value = {
            "total": 3,
            "passed": 2,
            "failed": 1,
            "warnings": [],
            "errors": ["Test failed: not_null check"],
            "test_results": [],
        }
        mock_executor_class.return_value = mock_executor

        # Capture both stdout and stderr (typer.echo with err=True writes to stderr)
        with (
            patch("sys.stdout", new=StringIO()) as fake_out,
            patch("sys.stderr", new=StringIO()) as fake_err,
        ):
            try:
                cmd_test(mock_args)
            except (SystemExit, typer.Exit) as e:
                # Should exit with 1 on failure
                exit_code = getattr(e, "exit_code", getattr(e, "code", 0))
                assert exit_code == 1

        output = fake_out.getvalue() + fake_err.getvalue()
        assert "Failed: 1" in output
        assert "Errors (1):" in output
        assert "Test execution failed with errors" in output

    @patch("t4t.cli.commands.test.TestExecutor")
    @patch("t4t.cli.commands.test.ExecutionEngine")
    @patch("t4t.cli.commands.test.ProjectParser")
    @patch("t4t.cli.commands.test.CommandContext")
    def test_cmd_test_with_warnings(
        self,
        mock_context_class,
        mock_parser_class,
        mock_engine_class,
        mock_executor_class,
        mock_args,
    ):
        """Test test command with warnings."""
        # Set up real project with SQL models
        models_sql = {
            "schema1.table1": "SELECT 1 as id, 'test' as name",
        }
        connection_config = {"type": "duckdb", "path": ":memory:"}
        project_path = self._setup_real_project(
            Path(mock_args.project_folder), models_sql, connection_config
        )

        # Setup mocks
        mock_ctx = Mock()
        mock_ctx.project_path = project_path
        mock_ctx.vars = {}
        mock_ctx.select_patterns = None
        mock_ctx.exclude_patterns = None
        mock_ctx.config = {"connection": connection_config}
        mock_ctx.print_variables_info = Mock()
        mock_ctx.print_selection_info = Mock()
        mock_context_class.return_value = mock_ctx

        # Mock parser (for dependency graph building - real OTS modules will be loaded)
        mock_parser = Mock()
        mock_parser.build_dependency_graph.return_value = {"nodes": ["schema1.table1"]}
        mock_parser.get_execution_order.return_value = ["schema1.table1"]
        mock_parser_class.return_value = mock_parser

        # Mock execution engine
        mock_engine = Mock()
        mock_adapter = Mock()
        mock_adapter.config.type = "duckdb"
        mock_engine.adapter = mock_adapter
        mock_engine_class.return_value = mock_engine

        # Mock test executor with warnings
        mock_executor = Mock()
        mock_executor.execute_all_tests.return_value = {
            "total": 2,
            "passed": 2,
            "failed": 0,
            "warnings": ["Warning: Table has no primary key"],
            "errors": [],
            "test_results": [],
        }
        mock_executor_class.return_value = mock_executor

        # Capture stdout
        with (
            patch("sys.stdout", new=StringIO()) as fake_out,
            contextlib.suppress(SystemExit),  # should not exit on warnings
        ):
            cmd_test(mock_args)

        output = fake_out.getvalue()
        assert "Warnings (1):" in output
        assert "Test execution completed with warnings" in output

    @patch("t4t.cli.commands.test.TestExecutor")
    @patch("t4t.cli.commands.test.ExecutionEngine")
    @patch("t4t.cli.commands.test.ProjectParser")
    @patch("t4t.cli.commands.test.ModelSelector")
    @patch("t4t.cli.commands.test.CommandContext")
    def test_cmd_test_with_selection_patterns(
        self,
        mock_context_class,
        mock_selector_class,
        mock_parser_class,
        mock_engine_class,
        mock_executor_class,
        mock_args,
    ):
        """Test test command with select/exclude patterns."""
        # Set up real project with SQL models
        models_sql = {
            "schema1.table1": "SELECT 1 as id, 'test' as name",
            "schema1.temp": "SELECT 2 as id, 'temp' as name",
        }
        connection_config = {"type": "duckdb", "path": ":memory:"}
        project_path = self._setup_real_project(
            Path(mock_args.project_folder), models_sql, connection_config
        )

        # Setup mocks
        mock_ctx = Mock()
        mock_ctx.project_path = project_path
        mock_ctx.vars = {}
        mock_ctx.select_patterns = ["schema1.*"]
        mock_ctx.exclude_patterns = ["*.temp"]
        mock_ctx.config = {"connection": connection_config}
        mock_ctx.print_variables_info = Mock()
        mock_ctx.print_selection_info = Mock()
        mock_context_class.return_value = mock_ctx

        # Mock parser (for dependency graph building - real OTS modules will be loaded)
        mock_parser = Mock()
        mock_parser.build_dependency_graph.return_value = {
            "nodes": ["schema1.table1", "schema1.temp"]
        }
        mock_parser.get_execution_order.return_value = ["schema1.table1", "schema1.temp"]
        mock_parser_class.return_value = mock_parser

        # Mock selector
        mock_selector = Mock()
        filtered_models = {"schema1.table1": {}}
        filtered_order = ["schema1.table1"]
        mock_selector.filter_models.return_value = (filtered_models, filtered_order)
        mock_selector_class.return_value = mock_selector

        # Mock execution engine
        mock_engine = Mock()
        mock_adapter = Mock()
        mock_adapter.config.type = "duckdb"
        mock_engine.adapter = mock_adapter
        mock_engine_class.return_value = mock_engine

        # Mock test executor
        mock_executor = Mock()
        mock_executor.execute_all_tests.return_value = {
            "total": 1,
            "passed": 1,
            "failed": 0,
            "warnings": [],
            "errors": [],
            "test_results": [],
        }
        mock_executor_class.return_value = mock_executor

        # Capture stdout
        with (
            patch("sys.stdout", new=StringIO()) as fake_out,
            contextlib.suppress(SystemExit),
        ):
            cmd_test(mock_args)

        output = fake_out.getvalue()
        assert "Filtered to 1 models" in output

    @patch("t4t.cli.commands.test.TestExecutor")
    @patch("t4t.cli.commands.test.ExecutionEngine")
    @patch("t4t.cli.commands.test.ProjectParser")
    @patch("t4t.cli.commands.test.CommandContext")
    def test_cmd_test_verbose_mode(
        self,
        mock_context_class,
        mock_parser_class,
        mock_engine_class,
        mock_executor_class,
        mock_args,
    ):
        """Test test command with verbose output."""
        # Set up real project with SQL models
        models_sql = {
            "schema1.table1": "SELECT 1 as id, 'test' as name",
        }
        connection_config = {"type": "duckdb", "path": ":memory:"}
        project_path = self._setup_real_project(
            Path(mock_args.project_folder), models_sql, connection_config
        )

        # Setup mocks
        mock_ctx = Mock()
        mock_ctx.project_path = project_path
        mock_ctx.vars = {}
        mock_ctx.select_patterns = None
        mock_ctx.exclude_patterns = None
        mock_ctx.config = {"connection": connection_config}
        mock_ctx.verbose = True
        mock_ctx.print_variables_info = Mock()
        mock_ctx.print_selection_info = Mock()
        mock_context_class.return_value = mock_ctx

        # Mock parser (for dependency graph building - real OTS modules will be loaded)
        mock_parser = Mock()
        mock_parser.build_dependency_graph.return_value = {"nodes": ["schema1.table1"]}
        mock_parser.get_execution_order.return_value = ["schema1.table1"]
        mock_parser_class.return_value = mock_parser

        # Mock execution engine
        mock_engine = Mock()
        mock_adapter = Mock()
        mock_adapter.config.type = "duckdb"
        mock_engine.adapter = mock_adapter
        mock_engine_class.return_value = mock_engine

        # Mock test executor with detailed results
        mock_executor = Mock()
        mock_executor.execute_all_tests.return_value = {
            "total": 1,
            "passed": 1,
            "failed": 0,
            "warnings": [],
            "errors": [],
            "test_results": ["Test passed: not_null on schema1.table1.id"],
        }
        mock_executor_class.return_value = mock_executor

        # Capture stdout
        with (
            patch("sys.stdout", new=StringIO()) as fake_out,
            contextlib.suppress(SystemExit),
        ):
            cmd_test(mock_args)

        output = fake_out.getvalue()
        assert "Detailed Results:" in output

    @patch("t4t.cli.commands.test.TestExecutor")
    @patch("t4t.cli.commands.test.ExecutionEngine")
    @patch("t4t.cli.commands.test.ProjectParser")
    @patch("t4t.cli.commands.test.CommandContext")
    def test_cmd_test_handles_exceptions(
        self,
        mock_context_class,
        mock_parser_class,
        mock_engine_class,
        mock_executor_class,
        mock_args,
    ):
        """Test test command handles exceptions gracefully."""
        # Set up real project with SQL models
        models_sql = {
            "schema1.table1": "SELECT 1 as id, 'test' as name",
        }
        connection_config = {"type": "duckdb", "path": ":memory:"}
        project_path = self._setup_real_project(
            Path(mock_args.project_folder), models_sql, connection_config
        )

        # Setup mocks
        mock_ctx = Mock()
        mock_ctx.project_path = project_path
        mock_ctx.vars = {}
        mock_ctx.config = {"connection": connection_config}
        mock_ctx.print_variables_info = Mock()
        mock_ctx.print_selection_info = Mock()
        mock_ctx.handle_error = Mock()
        mock_context_class.return_value = mock_ctx

        # Mock parser that raises exception during dependency graph building
        mock_parser = Mock()
        mock_parser.build_dependency_graph.side_effect = Exception("Parse failed")
        mock_parser_class.return_value = mock_parser

        # Capture stdout
        with patch("sys.stdout", new=StringIO()):
            cmd_test(mock_args)

        # Verify error was handled
        mock_ctx.handle_error.assert_called_once()

    @patch("t4t.cli.commands.test.TestExecutor")
    @patch("t4t.cli.commands.test.ExecutionEngine")
    @patch("t4t.cli.commands.test.ProjectParser")
    @patch("t4t.cli.commands.test.CommandContext")
    def test_cmd_test_cleanup_execution_engine(
        self,
        mock_context_class,
        mock_parser_class,
        mock_engine_class,
        mock_executor_class,
        mock_args,
    ):
        """Test that execution engine is disconnected."""
        # Set up real project with SQL models
        models_sql = {
            "schema1.table1": "SELECT 1 as id, 'test' as name",
        }
        connection_config = {"type": "duckdb", "path": ":memory:"}
        project_path = self._setup_real_project(
            Path(mock_args.project_folder), models_sql, connection_config
        )

        # Setup mocks
        mock_ctx = Mock()
        mock_ctx.project_path = project_path
        mock_ctx.vars = {}
        mock_ctx.select_patterns = None
        mock_ctx.exclude_patterns = None
        mock_ctx.config = {"connection": connection_config}
        mock_ctx.print_variables_info = Mock()
        mock_ctx.print_selection_info = Mock()
        mock_context_class.return_value = mock_ctx

        # Mock parser (for dependency graph building - real OTS modules will be loaded)
        mock_parser = Mock()
        mock_parser.build_dependency_graph.return_value = {"nodes": ["schema1.table1"]}
        mock_parser.get_execution_order.return_value = ["schema1.table1"]
        mock_parser_class.return_value = mock_parser

        # Mock execution engine
        mock_engine = Mock()
        mock_adapter = Mock()
        mock_adapter.config.type = "duckdb"
        mock_engine.adapter = mock_adapter
        mock_engine_class.return_value = mock_engine

        # Mock test executor
        mock_executor = Mock()
        mock_executor.execute_all_tests.return_value = {
            "total": 1,
            "passed": 1,
            "failed": 0,
            "warnings": [],
            "errors": [],
            "test_results": [],
        }
        mock_executor_class.return_value = mock_executor

        # Capture stdout
        with patch("sys.stdout", new=StringIO()), contextlib.suppress(SystemExit):
            cmd_test(mock_args)

        # Verify disconnect was called
        mock_engine.disconnect.assert_called_once()

    @patch("t4t.cli.commands.test.TestExecutor")
    @patch("t4t.cli.commands.test.ExecutionEngine")
    @patch("t4t.cli.commands.test.ProjectParser")
    @patch("t4t.cli.commands.test.CommandContext")
    def test_cmd_test_relative_path_resolution(
        self,
        mock_context_class,
        mock_parser_class,
        mock_engine_class,
        mock_executor_class,
        mock_args,
    ):
        """Test that relative paths in connection config are resolved."""
        # Set up real project with SQL models
        models_sql = {
            "schema1.table1": "SELECT 1 as id, 'test' as name",
        }
        connection_config = {"type": "duckdb", "path": ":memory:"}
        project_path = self._setup_real_project(
            Path(mock_args.project_folder), models_sql, connection_config
        )

        # Setup mocks
        mock_ctx = Mock()
        mock_ctx.project_path = project_path
        mock_ctx.vars = {}
        mock_ctx.select_patterns = None
        mock_ctx.exclude_patterns = None
        mock_ctx.config = {"connection": {"type": "duckdb", "path": "data/test.duckdb"}}
        mock_ctx.print_variables_info = Mock()
        mock_ctx.print_selection_info = Mock()
        mock_context_class.return_value = mock_ctx

        # Mock parser (for dependency graph building - real OTS modules will be loaded)
        mock_parser = Mock()
        mock_parser.build_dependency_graph.return_value = {"nodes": ["schema1.table1"]}
        mock_parser.get_execution_order.return_value = ["schema1.table1"]
        mock_parser_class.return_value = mock_parser

        # Mock execution engine
        mock_engine = Mock()
        mock_adapter = Mock()
        mock_adapter.config.type = "duckdb"
        mock_engine.adapter = mock_adapter
        mock_engine_class.return_value = mock_engine

        # Mock test executor
        mock_executor = Mock()
        mock_executor.execute_all_tests.return_value = {
            "total": 1,
            "passed": 1,
            "failed": 0,
            "warnings": [],
            "errors": [],
            "test_results": [],
        }
        mock_executor_class.return_value = mock_executor

        # Capture stdout
        with patch("sys.stdout", new=StringIO()), contextlib.suppress(SystemExit):
            cmd_test(mock_args)

        # Verify ExecutionEngine was called with resolved path
        call_args = mock_engine_class.call_args
        assert call_args.kwargs["config"]["path"] == str(mock_ctx.project_path / "data/test.duckdb")
