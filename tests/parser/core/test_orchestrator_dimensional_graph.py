"""
Targeted tests for ParserOrchestrator dimensional graph branches.
"""

from pathlib import Path
from unittest.mock import Mock

from tee.parser.core.orchestrator import ParserOrchestrator
from tee.parser.shared.dimension_registry import build_dimension_registry_from_models


def _orchestrator(tmp_path):
    (tmp_path / "models").mkdir()
    return ParserOrchestrator(
        project_folder=str(tmp_path),
        connection={"type": "duckdb"},
        project_config={},
    )


def test_build_dimensional_graph_returns_cached_when_no_override(tmp_path):
    orchestrator = _orchestrator(tmp_path)
    orchestrator._dimensional_graph = {"cached": True}
    orchestrator.dimensional_builder.build_graph = Mock(return_value={"cached": False})

    result = orchestrator.build_dimensional_graph()

    assert result == {"cached": True}
    orchestrator.dimensional_builder.build_graph.assert_not_called()


def test_build_dimensional_graph_passes_auto_built_dimension_registry(tmp_path):
    """Orchestrator forwards the registry derived from parsed dimension models."""
    orchestrator = _orchestrator(tmp_path)
    orchestrator._parsed_models = {
        "dwh.dim_date": {
            "model_metadata": {"metadata": {"table_type": "dim", "schema": []}},
        },
        "dwh.fct_sales": {
            "model_metadata": {"metadata": {"table_type": "fact", "schema": []}},
        },
    }
    orchestrator._dimension_registry = build_dimension_registry_from_models(
        orchestrator._parsed_models
    )
    orchestrator.dimensional_builder.build_graph = Mock(return_value={"ok": True})

    orchestrator.build_dimensional_graph()

    orchestrator.dimensional_builder.build_graph.assert_called_once()
    _args, kwargs = orchestrator.dimensional_builder.build_graph.call_args
    assert kwargs["dimension_registry"] == {"date": "dwh.dim_date"}


def test_build_dimensional_graph_override_bypasses_cache(tmp_path):
    orchestrator = _orchestrator(tmp_path)
    orchestrator._dimensional_graph = {"cached": True}
    orchestrator._parsed_models = {"dwh.fct_sales": {"model_metadata": {"metadata": {}}}}
    orchestrator.dimensional_builder.build_graph = Mock(return_value={"override": True})

    result = orchestrator.build_dimensional_graph(infer_from_column_names=True)

    assert result == {"override": True}
    # Override calls builder even if cache exists.
    orchestrator.dimensional_builder.build_graph.assert_called_once()
    # Cache remains unchanged for override calls.
    assert orchestrator._dimensional_graph == {"cached": True}


def test_export_all_includes_dimensional_graph_artifact(tmp_path):
    orchestrator = _orchestrator(tmp_path)

    parsed_models = {"dwh.fct_sales": {"model_metadata": {"metadata": {}}}}
    dependency_graph = {
        "nodes": ["dwh.fct_sales"],
        "edges": [],
        "dependencies": {},
        "dependents": {},
        "execution_order": [],
        "cycles": [],
    }
    dimensional_graph = {
        "facts": ["dwh.fct_sales"],
        "dimensions": [],
        "relationships": [],
        "grain": {},
        "diagnostics": {},
    }

    orchestrator.discover_and_parse_models = Mock(return_value=parsed_models)
    orchestrator.build_dependency_graph = Mock(return_value=dependency_graph)
    orchestrator.build_dimensional_graph = Mock(return_value=dimensional_graph)
    orchestrator.json_exporter.export_all = Mock(
        return_value={
            "parsed_models": Path("parsed_models.json"),
            "dependency_graph": Path("dependency_graph.json"),
        }
    )
    orchestrator.json_exporter.export_dimensional_graph = Mock(
        return_value=Path("dimensional_graph.json")
    )
    orchestrator.report_generator.generate_all_reports = Mock(
        return_value={"markdown_report": Path("dependency_report.md")}
    )

    results = orchestrator.export_all()

    assert "dimensional_graph" in results
    assert results["dimensional_graph"] == Path("dimensional_graph.json")
    orchestrator.json_exporter.export_dimensional_graph.assert_called_once_with(dimensional_graph)
