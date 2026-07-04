"""
Unit tests for the docs CLI command.
"""

from pathlib import Path
from unittest.mock import Mock, patch

from typer.testing import CliRunner

from t4t.cli.commands.docs import cmd_docs
from t4t.cli.main import app


class TestDocsCommand:
    """Test cases for docs command."""

    @patch("t4t.cli.commands.docs.DocsGenerator")
    @patch("t4t.cli.commands.docs.ProjectParser")
    @patch("t4t.cli.commands.docs.generate_lookups")
    @patch("t4t.cli.commands.docs.CommandContext")
    def test_cmd_docs_generates_lookups_by_default(
        self,
        mock_context_class,
        mock_generate_lookups,
        mock_project_parser_class,
        mock_docs_generator_class,
    ):
        """Docs command should refresh lookups unless explicitly skipped."""
        mock_ctx = Mock()
        mock_ctx.project_path = Path("/tmp/test_project")
        mock_ctx.vars = {}
        mock_ctx.config = {"connection": {"type": "duckdb", "path": ":memory:"}}
        mock_ctx.print_variables_info = Mock()
        mock_context_class.return_value = mock_ctx

        mock_parser = Mock()
        mock_parser.collect_models.return_value = {"dwh.dim_shop": {"name": "dim_shop"}}
        mock_parser.build_dependency_graph.return_value = {"nodes": [], "edges": []}
        mock_parser.orchestrator.discover_and_parse_functions.return_value = {}
        mock_parser.orchestrator.build_dimensional_graph.return_value = {
            "facts": [],
            "dimensions": [],
            "relationships": [],
            "grain": {},
            "diagnostics": {},
        }
        mock_project_parser_class.return_value = mock_parser

        mock_generator = Mock()
        mock_docs_generator_class.return_value = mock_generator

        cmd_docs(project_folder=str(mock_ctx.project_path))

        mock_generate_lookups.assert_called_once_with(
            project_path=mock_ctx.project_path,
            vars_dict=mock_ctx.vars,
            auto_resolve_level_conflicts=True,
        )
        mock_parser.orchestrator.build_dimensional_graph.assert_called_once_with(
            infer_from_column_names=False
        )
        mock_generator.generate.assert_called_once()

    @patch("t4t.cli.commands.docs.DocsGenerator")
    @patch("t4t.cli.commands.docs.ProjectParser")
    @patch("t4t.cli.commands.docs.generate_lookups")
    @patch("t4t.cli.commands.docs._clean_generated_lookup_dirs")
    @patch("t4t.cli.commands.docs.CommandContext")
    def test_cmd_docs_skips_lookup_generation_when_requested(
        self,
        mock_context_class,
        mock_clean_generated_lookup_dirs,
        mock_generate_lookups,
        mock_project_parser_class,
        mock_docs_generator_class,
    ):
        """Docs command should not refresh lookups when skip_lookups=True."""
        mock_ctx = Mock()
        mock_ctx.project_path = Path("/tmp/test_project")
        mock_ctx.vars = {}
        mock_ctx.config = {"connection": {"type": "duckdb", "path": ":memory:"}}
        mock_ctx.print_variables_info = Mock()
        mock_context_class.return_value = mock_ctx

        mock_parser = Mock()
        mock_parser.collect_models.return_value = {
            "dwh.dim_shop": {
                "model_metadata": {"metadata": {"table_type": "dim"}},
            },
            "dwh.lkp_region": {
                "model_metadata": {"metadata": {"table_type": "lookup"}},
            },
        }
        mock_parser.build_dependency_graph.return_value = {
            "nodes": [
                {"id": "dwh.dim_shop"},
                {"id": "dwh.lkp_region"},
            ],
            "edges": [
                {"source": "dwh.dim_shop", "target": "dwh.lkp_region"},
            ],
            "sql_edges": [
                {"source": "dwh.dim_shop", "target": "dwh.lkp_region"},
            ],
            "dependencies": {
                "dwh.dim_shop": ["dwh.lkp_region"],
                "dwh.lkp_region": [],
            },
            "dependents": {
                "dwh.dim_shop": [],
                "dwh.lkp_region": ["dwh.dim_shop"],
            },
            "execution_order": ["dwh.dim_shop", "dwh.lkp_region"],
        }
        mock_parser.orchestrator.discover_and_parse_functions.return_value = {}
        mock_parser.orchestrator.build_dimensional_graph.return_value = {
            "facts": [],
            "dimensions": ["dwh.dim_shop", "dwh.lkp_region"],
            "relationships": [],
            "grain": {},
            "diagnostics": {},
        }
        mock_project_parser_class.return_value = mock_parser

        mock_generator = Mock()
        mock_docs_generator_class.return_value = mock_generator

        cmd_docs(project_folder=str(mock_ctx.project_path), skip_lookups=True)

        mock_generate_lookups.assert_not_called()
        mock_clean_generated_lookup_dirs.assert_called_once_with(mock_ctx.project_path)
        mock_parser.orchestrator.build_dimensional_graph.assert_called_once_with(
            infer_from_column_names=False
        )
        mock_generator.generate.assert_called_once()
        generator_kwargs = mock_docs_generator_class.call_args.kwargs
        assert set(generator_kwargs["parsed_models"].keys()) == {"dwh.dim_shop"}
        assert generator_kwargs["dependency_graph"]["nodes"] == [{"id": "dwh.dim_shop"}]
        assert generator_kwargs["dimensional_graph"]["dimensions"] == ["dwh.dim_shop"]

    @patch("t4t.cli.commands.docs.DocsGenerator")
    @patch("t4t.cli.commands.docs.ProjectParser")
    @patch("t4t.cli.commands.docs.generate_lookups")
    @patch("t4t.cli.commands.docs.CommandContext")
    def test_cmd_docs_forwards_inference_flag_to_builder(
        self,
        mock_context_class,
        _mock_generate_lookups,
        mock_project_parser_class,
        _mock_docs_generator_class,
    ):
        """cmd_docs should pass infer_dim_from_column_names through to builder."""
        mock_ctx = Mock()
        mock_ctx.project_path = Path("/tmp/test_project")
        mock_ctx.vars = {}
        mock_ctx.config = {"connection": {"type": "duckdb", "path": ":memory:"}}
        mock_ctx.print_variables_info = Mock()
        mock_context_class.return_value = mock_ctx

        mock_parser = Mock()
        mock_parser.collect_models.return_value = {"dwh.dim_shop": {"name": "dim_shop"}}
        mock_parser.build_dependency_graph.return_value = {"nodes": [], "edges": []}
        mock_parser.orchestrator.discover_and_parse_functions.return_value = {}
        mock_parser.orchestrator.build_dimensional_graph.return_value = {
            "facts": [],
            "dimensions": [],
            "relationships": [],
            "grain": {},
            "diagnostics": {},
        }
        mock_project_parser_class.return_value = mock_parser

        cmd_docs(project_folder=str(mock_ctx.project_path), infer_dim_from_column_names=True)

        mock_parser.orchestrator.build_dimensional_graph.assert_called_once_with(
            infer_from_column_names=True
        )


class TestDocsCliWiring:
    """Tests for docs option wiring in main CLI."""

    def test_docs_cli_forwards_skip_lookups_flag(self):
        """The --skip-lookups CLI option should be forwarded to cmd_docs."""
        runner = CliRunner()
        with patch("t4t.cli.main.cmd_docs") as mock_cmd_docs:
            result = runner.invoke(app, ["docs", "/tmp/test_project", "--skip-lookups"])

        assert result.exit_code == 0
        assert mock_cmd_docs.called
        assert mock_cmd_docs.call_args.kwargs["skip_lookups"] is True

    def test_docs_cli_forwards_infer_dimensional_flag(self):
        """The inference CLI option should be forwarded to cmd_docs."""
        runner = CliRunner()
        with patch("t4t.cli.main.cmd_docs") as mock_cmd_docs:
            result = runner.invoke(
                app,
                ["docs", "/tmp/test_project", "--infer-dim-from-column-names"],
            )

        assert result.exit_code == 0
        assert mock_cmd_docs.called
        assert mock_cmd_docs.call_args.kwargs["infer_dim_from_column_names"] is True
