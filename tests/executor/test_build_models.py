"""
Unit tests for build_models function.
"""

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest

from t4t.executor import build_models
from t4t.testing.base import TestResult, TestSeverity


class TestBuildModels:
    """Test cases for build_models function."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def mock_connection_config(self):
        """Create mock connection configuration."""
        return {
            "type": "duckdb",
            "path": ":memory:",
        }

    def _setup_parser_mock(self, parsed_models, execution_order, graph=None):
        """Helper to set up parser mock."""
        mock_parser = Mock()
        mock_parser.collect_models.return_value = parsed_models
        # Set parsed_functions as a dict (not Mock) to support len() calls
        mock_parser.parsed_functions = {}
        # Make sure parsed_functions can be checked with isinstance
        # Ensure it's a real dict, not a Mock
        if hasattr(mock_parser, "parsed_functions") and not isinstance(
            mock_parser.parsed_functions, dict
        ):
            mock_parser.parsed_functions = {}
        if graph is None:
            graph = {
                "nodes": list(parsed_models.keys()),
                "dependencies": {k: [] for k in parsed_models},
            }
        mock_parser.build_dependency_graph.return_value = graph
        mock_parser.get_execution_order.return_value = execution_order
        mock_parser.get_table_dependents.return_value = []
        mock_parser.orchestrator = Mock()
        mock_parser.orchestrator.evaluate_python_models.return_value = parsed_models
        mock_parser.orchestrator.discover_and_parse_functions.return_value = {}  # Return empty dict, not Mock
        return mock_parser

    def _setup_execution_engine_mock(self, execute_models_return):
        """Helper to set up execution engine mock."""
        mock_execution_engine = Mock()
        mock_execution_engine.execute_models.return_value = execute_models_return
        mock_execution_engine.execute_functions.return_value = {
            "executed_functions": [],
            "failed_functions": [],
        }
        mock_execution_engine.adapter = Mock()
        return mock_execution_engine

    def _setup_real_project(
        self, temp_dir, models_sql: dict[str, str], connection_config: dict[str, Any]
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
            f'name = "test_project"\n[environments.dev.connection]\ntype = "{connection_config["type"]}"\n{path_config}\n'
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

    @patch("t4t.executor_helpers.build_helpers.ModelExecutor")
    @patch("t4t.executor_helpers.build_helpers.ProjectParser")
    @patch("t4t.executor_helpers.build_helpers.TestExecutor")
    @patch("t4t.engine.execution_engine.ExecutionEngine")
    def test_build_models_success(
        self,
        mock_execution_engine_class,
        mock_test_executor_class,
        mock_parser_class,
        mock_model_executor_class,
        temp_dir,
        mock_connection_config,
    ):
        """Test successful build_models execution with real compilation."""
        # Set up real project with SQL models
        models_sql = {
            "schema1.table1": "SELECT 1 as id, 'test' as name",
            "schema1.table2": "SELECT id, name FROM schema1.table1",
        }
        project_path = self._setup_real_project(temp_dir, models_sql, mock_connection_config)

        # The real compilation has already happened, so build_models will load real OTS modules
        # We still need to mock the execution parts
        parsed_models = {
            "schema1.table1": {"model_metadata": {"metadata": {}}},
            "schema1.table2": {"model_metadata": {"metadata": {}}},
        }
        execution_order = ["schema1.table1", "schema1.table2"]

        # Setup parser mock (for dependency graph building)
        mock_parser = self._setup_parser_mock(parsed_models, execution_order)
        mock_parser_class.return_value = mock_parser

        # Setup model executor mock
        mock_model_executor = Mock()
        mock_model_executor.config = mock_connection_config
        execute_models_return = {
            "executed_tables": ["schema1.table1", "schema1.table2"],
            "failed_tables": [],
            "table_info": {
                "schema1.table1": {"row_count": 10},
                "schema1.table2": {"row_count": 20},
            },
        }
        mock_execution_engine = self._setup_execution_engine_mock(execute_models_return)
        mock_model_executor.execution_engine = mock_execution_engine
        mock_model_executor_class.return_value = mock_model_executor

        # Setup execution engine mock (for the one created inside build_models)
        mock_execution_engine_instance = Mock()
        mock_execution_engine_instance.connect = Mock()
        mock_execution_engine_instance.execute_models = mock_execution_engine.execute_models
        mock_execution_engine_instance._extract_metadata = mock_execution_engine._extract_metadata
        mock_execution_engine_instance.adapter = mock_execution_engine.adapter
        mock_execution_engine_class.return_value = mock_execution_engine_instance

        # Setup test executor mock
        mock_test_executor = Mock()
        mock_test_executor.execute_tests_for_model.return_value = []
        mock_test_executor_class.return_value = mock_test_executor

        # Execute (build_models will compile first, then load real OTS modules)
        results = build_models(
            project_folder=str(project_path),
            connection_config=mock_connection_config,
            save_analysis=False,
            variables={},
            project_config={"name": "test_project", "connection": mock_connection_config},
        )

        # Verify results
        assert len(results["executed_tables"]) == 2
        assert len(results["failed_tables"]) == 0
        assert results["test_results"]["total"] == 0

    @patch("t4t.executor_helpers.build_helpers.ModelExecutor")
    @patch("t4t.executor_helpers.build_helpers.ProjectParser")
    @patch("t4t.executor_helpers.build_helpers.TestExecutor")
    @patch("t4t.engine.execution_engine.ExecutionEngine")
    def test_build_models_stops_on_test_failure(
        self,
        mock_execution_engine_class,
        mock_test_executor_class,
        mock_parser_class,
        mock_model_executor_class,
        temp_dir,
        mock_connection_config,
    ):
        """Test that build_models stops on ERROR severity test failure."""
        # Set up real project with SQL models
        models_sql = {
            "schema1.table1": "SELECT 1 as id, 'test' as name",
            "schema1.table2": "SELECT id, name FROM schema1.table1",
        }
        project_path = self._setup_real_project(temp_dir, models_sql, mock_connection_config)

        parsed_models = {
            "schema1.table1": {
                "model_metadata": {"metadata": {"schema": [], "tests": ["not_null"]}}
            },
            "schema1.table2": {"model_metadata": {"metadata": {"schema": []}}},
        }
        execution_order = ["schema1.table1", "schema1.table2"]

        # Setup parser mock (for dependency graph building)
        mock_parser = self._setup_parser_mock(parsed_models, execution_order)
        mock_parser.get_table_dependents.return_value = ["schema1.table2"]
        mock_parser_class.return_value = mock_parser

        # Setup model executor mock
        mock_model_executor = Mock()
        mock_model_executor.config = mock_connection_config
        execute_models_return = {
            "executed_tables": ["schema1.table1"],
            "failed_tables": [],
            "table_info": {"schema1.table1": {"row_count": 10}},
        }
        mock_execution_engine = self._setup_execution_engine_mock(execute_models_return)
        # Metadata extraction is now handled by MetadataExtractor, not ExecutionEngine
        mock_model_executor.execution_engine = mock_execution_engine
        mock_model_executor_class.return_value = mock_model_executor

        # Setup execution engine mock
        mock_execution_engine_instance = Mock()
        mock_execution_engine_instance.connect = Mock()
        mock_execution_engine_instance.execute_models = mock_execution_engine.execute_models
        mock_execution_engine_instance.execute_functions = mock_execution_engine.execute_functions
        mock_execution_engine_instance.adapter = mock_execution_engine.adapter
        mock_execution_engine_class.return_value = mock_execution_engine_instance

        # Create a failing test result
        failing_test = TestResult(
            test_name="not_null",
            table_name="schema1.table1",
            column_name="id",
            passed=False,
            rows_returned=5,
            severity=TestSeverity.ERROR,
            message="Test failed: 5 violations found",
        )

        mock_test_executor = Mock()
        mock_test_executor.execute_tests_for_model.return_value = [failing_test]
        mock_test_executor_class.return_value = mock_test_executor

        # Execute - should raise SystemExit
        with pytest.raises(SystemExit) as exc_info:
            build_models(
                project_folder=str(project_path),
                connection_config=mock_connection_config,
                save_analysis=False,
                variables={},
                project_config={"name": "test_project", "connection": mock_connection_config},
            )

        # Should exit with code 1
        assert exc_info.value.code == 1

        # Verify that second model was not executed
        assert mock_execution_engine.execute_models.call_count == 1

    @patch("t4t.executor_helpers.build_helpers.ModelExecutor")
    @patch("t4t.executor_helpers.build_helpers.ProjectParser")
    @patch("t4t.executor_helpers.build_helpers.TestExecutor")
    @patch("t4t.engine.execution_engine.ExecutionEngine")
    def test_build_models_continues_on_warning(
        self,
        mock_execution_engine_class,
        mock_test_executor_class,
        mock_parser_class,
        mock_model_executor_class,
        temp_dir,
        mock_connection_config,
    ):
        """Test that build_models continues on WARNING severity test failures."""
        # Set up real project with SQL models
        models_sql = {
            "schema1.table1": "SELECT 1 as id, 'test' as name",
            "schema1.table2": "SELECT id, name FROM schema1.table1",
        }
        project_path = self._setup_real_project(temp_dir, models_sql, mock_connection_config)

        parsed_models = {
            "schema1.table1": {
                "model_metadata": {"metadata": {"schema": [], "tests": ["check_minimum_rows"]}}
            },
            "schema1.table2": {"model_metadata": {"metadata": {"schema": []}}},
        }
        execution_order = ["schema1.table1", "schema1.table2"]

        # Setup parser mock (for dependency graph building)
        mock_parser = self._setup_parser_mock(parsed_models, execution_order)
        mock_parser_class.return_value = mock_parser

        # Setup model executor mock
        mock_model_executor = Mock()
        mock_model_executor.config = mock_connection_config
        execute_models_return = {
            "executed_tables": ["schema1.table1", "schema1.table2"],
            "failed_tables": [],
            "table_info": {
                "schema1.table1": {"row_count": 10},
                "schema1.table2": {"row_count": 20},
            },
        }
        mock_execution_engine = self._setup_execution_engine_mock(execute_models_return)
        # Metadata extraction is now handled by MetadataExtractor, not ExecutionEngine
        mock_model_executor.execution_engine = mock_execution_engine
        mock_model_executor_class.return_value = mock_model_executor

        # Setup execution engine mock
        mock_execution_engine_instance = Mock()
        mock_execution_engine_instance.connect = Mock()
        mock_execution_engine_instance.execute_models = mock_execution_engine.execute_models
        mock_execution_engine_instance.execute_functions = mock_execution_engine.execute_functions
        mock_execution_engine_instance.adapter = mock_execution_engine.adapter
        mock_execution_engine_class.return_value = mock_execution_engine_instance

        # Create a warning test result
        warning_test = TestResult(
            test_name="check_minimum_rows",
            table_name="schema1.table1",
            column_name=None,
            passed=False,
            rows_returned=1,
            severity=TestSeverity.WARNING,
            message="Warning: row count is low",
        )

        mock_test_executor = Mock()
        mock_test_executor.execute_tests_for_model.return_value = [warning_test]
        mock_test_executor_class.return_value = mock_test_executor

        # Execute - should not raise SystemExit
        results = build_models(
            project_folder=str(project_path),
            connection_config=mock_connection_config,
            save_analysis=False,
            variables={},
            project_config={"name": "test_project", "connection": mock_connection_config},
        )

        # Should complete successfully
        assert len(results["executed_tables"]) == 2
        # Warning count should be at least 1 (may include other warnings)
        assert results["test_results"]["warnings"] >= 1

    @patch("t4t.executor_helpers.build_helpers.ModelExecutor")
    @patch("t4t.executor_helpers.build_helpers.ProjectParser")
    @patch("t4t.executor_helpers.build_helpers.TestExecutor")
    @patch("t4t.engine.execution_engine.ExecutionEngine")
    def test_build_models_stops_on_model_failure(
        self,
        mock_execution_engine_class,
        mock_test_executor_class,
        mock_parser_class,
        mock_model_executor_class,
        temp_dir,
        mock_connection_config,
    ):
        """Test that build_models stops on model execution failure."""
        # Set up real project with SQL models
        models_sql = {
            "schema1.table1": "SELECT 1 as id, 'test' as name",
            "schema1.table2": "SELECT id, name FROM schema1.table1",
        }
        project_path = self._setup_real_project(temp_dir, models_sql, mock_connection_config)

        parsed_models = {
            "schema1.table1": {"model_metadata": {"metadata": {}}},
            "schema1.table2": {"model_metadata": {"metadata": {}}},
        }
        execution_order = ["schema1.table1", "schema1.table2"]

        # Setup parser mock (for dependency graph building)
        mock_parser = self._setup_parser_mock(parsed_models, execution_order)
        mock_parser.get_table_dependents.return_value = ["schema1.table2"]
        mock_parser_class.return_value = mock_parser

        # Setup model executor mock
        mock_model_executor = Mock()
        mock_model_executor.config = mock_connection_config
        execute_models_return = {
            "executed_tables": [],
            "failed_tables": [{"table": "schema1.table1", "error": "SQL syntax error"}],
            "table_info": {},
        }
        mock_execution_engine = self._setup_execution_engine_mock(execute_models_return)
        mock_model_executor.execution_engine = mock_execution_engine
        mock_model_executor_class.return_value = mock_model_executor

        # Setup execution engine mock - this is the one created inside build_models
        mock_execution_engine_instance = Mock()
        mock_execution_engine_instance.connect = Mock()
        # The execute_models should return the failed table
        mock_execution_engine_instance.execute_models.return_value = execute_models_return
        mock_execution_engine_instance._extract_metadata = Mock(return_value=None)
        mock_execution_engine_instance.adapter = Mock()
        mock_execution_engine_class.return_value = mock_execution_engine_instance

        mock_test_executor = Mock()
        mock_test_executor_class.return_value = mock_test_executor

        # Execute - model failure should be handled gracefully (continue to next)
        # The build will complete but with failed models
        results = build_models(
            project_folder=str(project_path),
            connection_config=mock_connection_config,
            save_analysis=False,
            variables={},
            project_config={"name": "test_project", "connection": mock_connection_config},
        )

        # Should have failed tables
        assert len(results["failed_tables"]) > 0
        assert any(f["table"] == "schema1.table1" for f in results["failed_tables"])

    @patch("t4t.executor_helpers.build_helpers.ModelExecutor")
    @patch("t4t.executor_helpers.build_helpers.ProjectParser")
    @patch("t4t.executor_helpers.build_helpers.TestExecutor")
    @patch("t4t.engine.execution_engine.ExecutionEngine")
    def test_build_models_skips_dependents_on_failure(
        self,
        mock_execution_engine_class,
        mock_test_executor_class,
        mock_parser_class,
        mock_model_executor_class,
        temp_dir,
        mock_connection_config,
    ):
        """Test that build_models skips dependents when a model fails."""
        # Set up real project with SQL models
        models_sql = {
            "schema1.table1": "SELECT 1 as id, 'test' as name",
            "schema1.table2": "SELECT id, name FROM schema1.table1",
            "schema1.table3": "SELECT id, name FROM schema1.table2",
        }
        project_path = self._setup_real_project(temp_dir, models_sql, mock_connection_config)

        parsed_models = {
            "schema1.table1": {"model_metadata": {"metadata": {}}},
            "schema1.table2": {"model_metadata": {"metadata": {}}},
            "schema1.table3": {"model_metadata": {"metadata": {}}},
        }
        execution_order = ["schema1.table1", "schema1.table2", "schema1.table3"]

        # Setup parser mock (for dependency graph building)
        mock_parser = self._setup_parser_mock(parsed_models, execution_order)
        mock_parser.get_table_dependents.return_value = ["schema1.table2", "schema1.table3"]
        mock_parser_class.return_value = mock_parser

        # Setup model executor mock
        mock_model_executor = Mock()
        mock_model_executor.config = mock_connection_config
        execute_models_return = {
            "executed_tables": [],
            "failed_tables": [{"table": "schema1.table1", "error": "SQL error"}],
            "table_info": {},
        }
        mock_execution_engine = self._setup_execution_engine_mock(execute_models_return)
        mock_model_executor.execution_engine = mock_execution_engine
        mock_model_executor_class.return_value = mock_model_executor

        # Setup execution engine mock
        mock_execution_engine_instance = Mock()
        mock_execution_engine_instance.connect = Mock()
        mock_execution_engine_instance.execute_models = mock_execution_engine.execute_models
        mock_execution_engine_instance.execute_functions = mock_execution_engine.execute_functions
        mock_execution_engine_instance.adapter = mock_execution_engine.adapter
        mock_execution_engine_class.return_value = mock_execution_engine_instance

        mock_test_executor = Mock()
        mock_test_executor_class.return_value = mock_test_executor

        # Execute - model failure should be handled gracefully
        results = build_models(
            project_folder=str(project_path),
            connection_config=mock_connection_config,
            save_analysis=False,
            variables={},
            project_config={"name": "test_project", "connection": mock_connection_config},
        )

        # Should have failed tables and skipped dependents
        assert len(results["failed_tables"]) > 0
        # Only the first model should have been attempted (dependents skipped)
        assert mock_execution_engine_instance.execute_models.call_count == 1

    @patch("t4t.executor_helpers.build_helpers.ModelExecutor")
    @patch("t4t.executor_helpers.build_helpers.ProjectParser")
    @patch("t4t.executor_helpers.build_helpers.TestExecutor")
    @patch("t4t.engine.execution_engine.ExecutionEngine")
    def test_build_models_interleaves_tests(
        self,
        mock_execution_engine_class,
        mock_test_executor_class,
        mock_parser_class,
        mock_model_executor_class,
        temp_dir,
        mock_connection_config,
    ):
        """Test that build_models executes tests immediately after each model."""
        # Set up real project with SQL models
        models_sql = {
            "schema1.table1": "SELECT 1 as id, 'test' as name",
            "schema1.table2": "SELECT id, name FROM schema1.table1",
        }
        project_path = self._setup_real_project(temp_dir, models_sql, mock_connection_config)

        parsed_models = {
            "schema1.table1": {
                "model_metadata": {"metadata": {"schema": [], "tests": ["not_null"]}}
            },
            "schema1.table2": {"model_metadata": {"metadata": {"schema": [], "tests": ["unique"]}}},
        }
        execution_order = ["schema1.table1", "schema1.table2"]

        # Setup parser mock (for dependency graph building)
        mock_parser = self._setup_parser_mock(parsed_models, execution_order)
        mock_parser_class.return_value = mock_parser

        # Setup model executor mock
        mock_model_executor = Mock()
        mock_model_executor.config = mock_connection_config
        execute_models_return = {
            "executed_tables": ["schema1.table1", "schema1.table2"],
            "failed_tables": [],
            "table_info": {
                "schema1.table1": {"row_count": 10},
                "schema1.table2": {"row_count": 20},
            },
        }
        mock_execution_engine = self._setup_execution_engine_mock(execute_models_return)
        # Metadata extraction is now handled by MetadataExtractor, not ExecutionEngine
        mock_model_executor.execution_engine = mock_execution_engine
        mock_model_executor_class.return_value = mock_model_executor

        # Setup execution engine mock
        mock_execution_engine_instance = Mock()
        mock_execution_engine_instance.connect = Mock()
        mock_execution_engine_instance.execute_models = mock_execution_engine.execute_models
        mock_execution_engine_instance.execute_functions = mock_execution_engine.execute_functions
        mock_execution_engine_instance.adapter = mock_execution_engine.adapter
        mock_execution_engine_class.return_value = mock_execution_engine_instance

        mock_test_executor = Mock()
        mock_test_executor.execute_tests_for_model.side_effect = [
            [
                TestResult(
                    test_name="not_null",
                    table_name="schema1.table1",
                    column_name=None,
                    passed=True,
                    rows_returned=0,
                    severity=TestSeverity.ERROR,
                    message="Passed",
                )
            ],
            [
                TestResult(
                    test_name="unique",
                    table_name="schema1.table2",
                    column_name=None,
                    passed=True,
                    rows_returned=0,
                    severity=TestSeverity.ERROR,
                    message="Passed",
                )
            ],
        ]
        mock_test_executor_class.return_value = mock_test_executor

        # Execute
        results = build_models(
            project_folder=str(project_path),
            connection_config=mock_connection_config,
            save_analysis=False,
            variables={},
            project_config={"name": "test_project", "connection": mock_connection_config},
        )

        # Verify tests were called for each model
        assert mock_test_executor.execute_tests_for_model.call_count == 2
        # Check that tests were called with correct table names
        # Access call arguments - can be positional or keyword
        call_args = []
        for call in mock_test_executor.execute_tests_for_model.call_args_list:
            if call[0]:  # positional args
                call_args.append(call[0][0])
            elif "table_name" in call[1]:  # keyword args
                call_args.append(call[1]["table_name"])
        assert "schema1.table1" in call_args
        assert "schema1.table2" in call_args

        # Verify results
        assert results["test_results"]["total"] == 2
        assert results["test_results"]["passed"] == 2

    @patch("t4t.executor_helpers.build_helpers.ModelExecutor")
    @patch("t4t.executor_helpers.build_helpers.ProjectParser")
    @patch("t4t.executor_helpers.build_helpers.TestExecutor")
    @patch("t4t.engine.execution_engine.ExecutionEngine")
    def test_build_models_skips_test_nodes(
        self,
        mock_execution_engine_class,
        mock_test_executor_class,
        mock_parser_class,
        mock_model_executor_class,
        temp_dir,
        mock_connection_config,
    ):
        """Test that build_models skips test nodes in execution order."""
        # Set up real project with SQL models
        models_sql = {
            "schema1.table1": "SELECT 1 as id, 'test' as name",
            "schema1.table2": "SELECT id, name FROM schema1.table1",
        }
        project_path = self._setup_real_project(temp_dir, models_sql, mock_connection_config)

        parsed_models = {
            "schema1.table1": {"model_metadata": {"metadata": {}}},
            "schema1.table2": {"model_metadata": {"metadata": {}}},
        }
        # Execution order includes test nodes
        execution_order = [
            "schema1.table1",
            "test:schema1.table1.not_null",
            "schema1.table2",
        ]

        # Setup parser mock (for dependency graph building)
        graph = {
            "nodes": ["schema1.table1", "test:schema1.table1.not_null", "schema1.table2"],
            "dependencies": {
                "schema1.table1": [],
                "test:schema1.table1.not_null": ["schema1.table1"],
                "schema1.table2": [],
            },
        }
        mock_parser = self._setup_parser_mock(parsed_models, execution_order, graph)
        mock_parser_class.return_value = mock_parser

        # Setup model executor mock
        mock_model_executor = Mock()
        mock_model_executor.config = mock_connection_config
        execute_models_return = {
            "executed_tables": ["schema1.table1", "schema1.table2"],
            "failed_tables": [],
            "table_info": {
                "schema1.table1": {"row_count": 10},
                "schema1.table2": {"row_count": 20},
            },
        }
        mock_execution_engine = self._setup_execution_engine_mock(execute_models_return)
        mock_model_executor.execution_engine = mock_execution_engine
        mock_model_executor_class.return_value = mock_model_executor

        # Setup execution engine mock
        mock_execution_engine_instance = Mock()
        mock_execution_engine_instance.connect = Mock()
        mock_execution_engine_instance.execute_models = mock_execution_engine.execute_models
        mock_execution_engine_instance.execute_functions = mock_execution_engine.execute_functions
        mock_execution_engine_instance.adapter = mock_execution_engine.adapter
        mock_execution_engine_class.return_value = mock_execution_engine_instance

        mock_test_executor = Mock()
        mock_test_executor.execute_tests_for_model.return_value = []
        mock_test_executor_class.return_value = mock_test_executor

        # Execute
        build_models(
            project_folder=str(project_path),
            connection_config=mock_connection_config,
            save_analysis=False,
            variables={},
            project_config={"name": "test_project", "connection": mock_connection_config},
        )

        # Verify that execute_models was only called for non-test nodes
        # Should be called twice (once for each table)
        assert mock_execution_engine.execute_models.call_count == 2
