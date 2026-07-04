"""Tests for dimension_registry JSON export."""

import json
from pathlib import Path

from t4t.parser.output.json_exporter import JSONExporter


def test_export_dimension_registry_writes_sorted_json(tmp_path: Path) -> None:
    exporter = JSONExporter(tmp_path)
    reg = {"date": "dwh.dim_date", "date.month": "dwh.dim_month"}
    out = exporter.export_dimension_registry(reg)
    assert out.exists()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded == {"date": "dwh.dim_date", "date.month": "dwh.dim_month"}


def test_export_all_includes_dimension_registry_when_passed(tmp_path: Path) -> None:
    exporter = JSONExporter(tmp_path)
    parsed = {"dwh.fct_x": {"model_metadata": {"metadata": {}}}}
    graph = {
        "nodes": [],
        "edges": [],
        "dependencies": {},
        "dependents": {},
        "execution_order": [],
        "cycles": [],
    }
    reg = {"date": "dwh.dim_date"}
    results = exporter.export_all(parsed, graph, dimension_registry=reg)
    assert "dimension_registry" in results
    assert results["dimension_registry"].name == "dimension_registry.json"
    data = json.loads(results["dimension_registry"].read_text(encoding="utf-8"))
    assert data == {"date": "dwh.dim_date"}
