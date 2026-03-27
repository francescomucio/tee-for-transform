"""
Fast integration-style tests for docs payload generation.
"""

import json
import re

from tee.parser.output.docs_generator import DocsGenerator


def _model(metadata: dict, sql: str = "select 1"):
    return {
        "model_metadata": {
            "table_name": "unused",
            "function_name": None,
            "description": metadata.get("description", "test model"),
            "variables": [],
            "metadata": metadata,
            "file_path": "models/test.sql",
        },
        "code": {
            "sql": {
                "original_sql": sql,
                "resolved_sql": sql,
                "operation_type": "select",
                "source_tables": [],
                "source_functions": [],
            }
        },
        "sqlglot_hash": "",
    }


def _extract_json(html: str, const_name: str) -> dict:
    pattern = rf"const {const_name} = (.*?);"
    m = re.search(pattern, html, flags=re.DOTALL)
    assert m, f"Could not find JS const '{const_name}' in html"
    return json.loads(m.group(1))


def test_docs_generator_embeds_dimensional_relationships(tmp_path):
    project_path = tmp_path / "project"
    output_path = tmp_path / "docs"
    project_path.mkdir()

    parsed_models = {
        "dwh.dim_customer": _model(
            {
                "table_type": "dim",
                "description": "Customer dimension",
                "schema": [
                    {"name": "customer_id", "datatype": "string", "tests": ["primary_key"]},
                ],
            }
        ),
        "dwh.fct_sales": _model(
            {
                "table_type": "fact",
                "description": "Sales fact",
                "schema": [
                    {"name": "customer_id", "datatype": "string"},
                ],
            }
        ),
    }

    dependency_graph = {
        "nodes": ["dwh.dim_customer", "dwh.fct_sales"],
        "edges": [("dwh.dim_customer", "dwh.fct_sales")],
        "sql_edges": [],
        "dependencies": {"dwh.fct_sales": ["dwh.dim_customer"], "dwh.dim_customer": []},
        "dependents": {"dwh.dim_customer": ["dwh.fct_sales"], "dwh.fct_sales": []},
        "execution_order": ["dwh.dim_customer", "dwh.fct_sales"],
        "cycles": [],
    }

    dimensional_graph = {
        "facts": ["dwh.fct_sales"],
        "dimensions": ["dwh.dim_customer"],
        "relationships": [
            {
                "source_fact": "dwh.fct_sales",
                "target_table": "dwh.dim_customer",
                "target_table_type": "dim",
                "fact_column": "customer_id",
                "target_column": "customer_id",
                "dimension_name": "Customer",
                "dimension_level": None,
                "semantic_level": None,
                "origin": "inferred_column_name",
                "confidence": "medium",
            }
        ],
        "grain": {"dwh.fct_sales": {"semantic_levels": [], "relationship_count": 1}},
        "diagnostics": {"inference_enabled": True, "unresolved_inferences": []},
    }

    generator = DocsGenerator(
        project_path=project_path,
        output_path=output_path,
        parsed_models=parsed_models,
        parsed_functions={},
        dependency_graph=dependency_graph,
        dimensional_graph=dimensional_graph,
    )
    generator.generate()

    index_html = (output_path / "index.html").read_text(encoding="utf-8")
    assert "dimensional_relationships" in index_html
    assert "inferred_column_name" in index_html

    graph_data = json.loads((output_path / "graph_data.json").read_text(encoding="utf-8"))
    assert "dimensional_relationships" in graph_data
    assert graph_data["dimensional_relationships"][0]["source_fact"] == "dwh.fct_sales"


def test_docs_generator_injects_fk_to_from_dimensional_relationship(tmp_path):
    project_path = tmp_path / "project"
    output_path = tmp_path / "docs"
    project_path.mkdir()

    parsed_models = {
        "dwh.dim_customer": _model(
            {
                "table_type": "dim",
                "schema": [{"name": "customer_id", "datatype": "string", "tests": ["primary_key"]}],
            }
        ),
        "dwh.fct_sales": _model(
            {
                "table_type": "fact",
                "schema": [
                    {"name": "customer_id", "datatype": "string"}
                ],  # no fk_to in source metadata
            }
        ),
    }
    dependency_graph = {
        "nodes": ["dwh.dim_customer", "dwh.fct_sales"],
        "edges": [],
        "sql_edges": [],
        "dependencies": {"dwh.fct_sales": [], "dwh.dim_customer": []},
        "dependents": {"dwh.dim_customer": [], "dwh.fct_sales": []},
        "execution_order": [],
        "cycles": [],
    }
    dimensional_graph = {
        "facts": ["dwh.fct_sales"],
        "dimensions": ["dwh.dim_customer"],
        "relationships": [
            {
                "source_fact": "dwh.fct_sales",
                "target_table": "dwh.dim_customer",
                "target_table_type": "dim",
                "fact_column": "customer_id",
                "target_column": "customer_id",
                "dimension_name": "Customer",
                "dimension_level": None,
                "semantic_level": None,
                "origin": "inferred_column_name",
                "confidence": "medium",
            }
        ],
        "grain": {},
        "diagnostics": {},
    }

    DocsGenerator(
        project_path=project_path,
        output_path=output_path,
        parsed_models=parsed_models,
        parsed_functions={},
        dependency_graph=dependency_graph,
        dimensional_graph=dimensional_graph,
    ).generate()

    index_html = (output_path / "index.html").read_text(encoding="utf-8")
    models_data = _extract_json(index_html, "modelsData")
    fct_cols = models_data["dwh.fct_sales"]["columns"]
    fk_col = next(c for c in fct_cols if c["name"] == "customer_id")
    assert fk_col["fk_to"] == {"table": "dwh.dim_customer", "column": "customer_id"}
    assert fk_col["type"] == "fk"


def test_docs_generator_adds_dimensional_edge_when_missing_and_dedupes_when_present(tmp_path):
    project_path = tmp_path / "project"
    output_path = tmp_path / "docs"
    project_path.mkdir()

    parsed_models = {
        "dwh.dim_customer": _model({"table_type": "dim", "schema": []}),
        "dwh.fct_sales": _model({"table_type": "fact", "schema": []}),
    }
    rel = {
        "source_fact": "dwh.fct_sales",
        "target_table": "dwh.dim_customer",
        "target_table_type": "dim",
        "fact_column": "customer_id",
        "target_column": "customer_id",
        "dimension_name": "Customer",
        "dimension_level": None,
        "semantic_level": None,
        "origin": "inferred_column_name",
        "confidence": "medium",
    }

    # Case A: missing edge in dependency graph -> should be added to graphData edges.
    DocsGenerator(
        project_path=project_path,
        output_path=output_path,
        parsed_models=parsed_models,
        parsed_functions={},
        dependency_graph={
            "nodes": ["dwh.dim_customer", "dwh.fct_sales"],
            "edges": [],
            "sql_edges": [],
            "dependencies": {},
            "dependents": {},
            "execution_order": [],
            "cycles": [],
        },
        dimensional_graph={
            "facts": [],
            "dimensions": [],
            "relationships": [rel],
            "grain": {},
            "diagnostics": {},
        },
    ).generate()
    html_a = (output_path / "index.html").read_text(encoding="utf-8")
    graph_data_a = _extract_json(html_a, "graphData")
    assert ["dwh.dim_customer", "dwh.fct_sales"] in graph_data_a["edges"]

    # Case B: edge already present -> should not duplicate.
    DocsGenerator(
        project_path=project_path,
        output_path=output_path,
        parsed_models=parsed_models,
        parsed_functions={},
        dependency_graph={
            "nodes": ["dwh.dim_customer", "dwh.fct_sales"],
            "edges": [("dwh.dim_customer", "dwh.fct_sales")],
            "sql_edges": [],
            "dependencies": {},
            "dependents": {},
            "execution_order": [],
            "cycles": [],
        },
        dimensional_graph={
            "facts": [],
            "dimensions": [],
            "relationships": [rel],
            "grain": {},
            "diagnostics": {},
        },
    ).generate()
    html_b = (output_path / "index.html").read_text(encoding="utf-8")
    graph_data_b = _extract_json(html_b, "graphData")
    assert graph_data_b["edges"].count(["dwh.dim_customer", "dwh.fct_sales"]) == 1
