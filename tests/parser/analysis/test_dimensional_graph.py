"""
Unit tests for dimensional relationship graph builder.
"""

import pytest

from tee.parser.analysis.dimensional_graph import DimensionalRelationshipGraphBuilder
from tee.parser.shared.dimension_registry import build_dimension_registry_from_models
from tee.parser.shared.exceptions import DimensionalGraphError


def _model(table_type, schema=None, hierarchy=None, conformed_dimension=None):
    meta: dict = {
        "table_type": table_type,
        "schema": schema or [],
    }
    if hierarchy is not None:
        meta["hierarchy"] = hierarchy
    if conformed_dimension is not None:
        meta["conformed_dimension"] = conformed_dimension
    return {
        "model_metadata": {
            "metadata": meta,
        },
        "code": {"sql": {"source_tables": []}},
    }


def test_build_graph_uses_declared_fk():
    parsed_models = {
        "dwh.dim_customer": _model(
            "dim",
            schema=[
                {"name": "customer_id", "datatype": "string", "tests": ["primary_key"]},
            ],
        ),
        "dwh.fct_sales": _model(
            "fact",
            schema=[
                {
                    "name": "customer_id",
                    "datatype": "string",
                    "fk_to": {"table": "dwh.dim_customer", "column": "customer_id"},
                }
            ],
        ),
    }

    graph = DimensionalRelationshipGraphBuilder().build_graph(parsed_models)
    assert graph["facts"] == ["dwh.fct_sales"]
    assert "dwh.dim_customer" in graph["dimensions"]
    assert len(graph["relationships"]) == 1
    rel = graph["relationships"][0]
    assert rel["origin"] == "declared_fk"
    assert rel["target_table"] == "dwh.dim_customer"
    assert rel["fact_column"] == "customer_id"


def test_build_graph_prefers_lookup_for_declared_dimension_level():
    parsed_models = {
        "dwh.dim_date": _model(
            "dim",
            schema=[
                {"name": "day_id", "datatype": "string", "tests": ["primary_key"]},
                {"name": "month_id", "datatype": "string", "tests": ["primary_key"]},
            ],
            hierarchy={
                "levels": [
                    {
                        "level_number": 1,
                        "name": "Day",
                        "column": "day_name",
                        "primary_key": "day_id",
                    },
                    {
                        "level_number": 2,
                        "name": "Month",
                        "column": "month_name",
                        "primary_key": "month_id",
                    },
                ]
            },
        ),
        "dwh.lkp_month": _model(
            "lookup",
            schema=[
                {"name": "month_id", "datatype": "string", "tests": ["primary_key"]},
            ],
            hierarchy={
                "levels": [
                    {
                        "level_number": 1,
                        "name": "Month",
                        "column": "month_name",
                        "primary_key": "month_id",
                    },
                ]
            },
        ),
        "dwh.fct_sales": _model(
            "fact",
            schema=[
                {"name": "month_id", "datatype": "string", "dimension": "date"},
            ],
        ),
    }

    graph = DimensionalRelationshipGraphBuilder(include_lookup=True).build_graph(parsed_models)
    assert len(graph["relationships"]) == 1
    rel = graph["relationships"][0]
    assert rel["origin"] == "declared_dimension"
    assert rel["target_table"] == "dwh.lkp_month"
    assert rel["dimension_name"] == "Date"
    assert rel["dimension_level"] == "Month"
    assert rel["semantic_level"] == "Date.Month"


def test_build_graph_infers_from_column_name_when_enabled():
    parsed_models = {
        "dwh.dim_article": _model(
            "dim",
            schema=[{"name": "article_id", "datatype": "string", "tests": ["primary_key"]}],
        ),
        "dwh.fct_sales": _model(
            "fact",
            schema=[{"name": "article_id", "datatype": "string"}],
        ),
    }

    graph = DimensionalRelationshipGraphBuilder(infer_from_column_names=True).build_graph(
        parsed_models
    )
    assert len(graph["relationships"]) == 1
    rel = graph["relationships"][0]
    assert rel["origin"] == "inferred_column_name"
    assert rel["target_table"] == "dwh.dim_article"
    assert rel["confidence"] == "medium"


def test_build_graph_does_not_infer_when_disabled():
    parsed_models = {
        "dwh.dim_article": _model(
            "dim",
            schema=[{"name": "article_id", "datatype": "string", "tests": ["primary_key"]}],
        ),
        "dwh.fct_sales": _model(
            "fact",
            schema=[{"name": "article_id", "datatype": "string"}],
        ),
    }

    graph = DimensionalRelationshipGraphBuilder(infer_from_column_names=False).build_graph(
        parsed_models
    )
    assert graph["relationships"] == []


def test_build_graph_raises_on_ambiguous_inference():
    parsed_models = {
        "dwh.dim_customer": _model(
            "dim",
            schema=[{"name": "customer_id", "datatype": "string", "tests": ["primary_key"]}],
        ),
        "dwh.dim_customer_alt": _model(
            "dim",
            schema=[{"name": "customer_id", "datatype": "string", "tests": ["primary_key"]}],
        ),
        "dwh.fct_sales": _model(
            "fact",
            schema=[{"name": "customer_id", "datatype": "string"}],
        ),
    }

    builder = DimensionalRelationshipGraphBuilder(infer_from_column_names=True)
    with pytest.raises(DimensionalGraphError):
        builder.build_graph(parsed_models)


def test_declared_dimension_requires_explicit_pk_metadata():
    parsed_models = {
        "dwh.dim_date": _model(
            "dim",
            schema=[{"name": "month_id", "datatype": "string"}],  # not marked as primary key
        ),
        "dwh.fct_sales": _model(
            "fact",
            schema=[{"name": "month_id", "datatype": "string", "dimension": "date"}],
        ),
    }

    builder = DimensionalRelationshipGraphBuilder()
    with pytest.raises(DimensionalGraphError):
        builder.build_graph(parsed_models)


def test_declared_dimension_without_lookup_when_include_lookup_disabled():
    parsed_models = {
        "dwh.dim_date": _model(
            "dim",
            schema=[{"name": "month_id", "datatype": "string", "tests": ["primary_key"]}],
            hierarchy={
                "levels": [
                    {
                        "level_number": 1,
                        "name": "Month",
                        "column": "month_name",
                        "primary_key": "month_id",
                    },
                ]
            },
        ),
        "dwh.lkp_month": _model(
            "lookup",
            schema=[{"name": "month_id", "datatype": "string", "tests": ["primary_key"]}],
            hierarchy={
                "levels": [
                    {
                        "level_number": 1,
                        "name": "Month",
                        "column": "month_name",
                        "primary_key": "month_id",
                    },
                ]
            },
        ),
        "dwh.fct_sales": _model(
            "fact",
            schema=[{"name": "month_id", "datatype": "string", "dimension": "date"}],
        ),
    }

    graph = DimensionalRelationshipGraphBuilder(include_lookup=False).build_graph(parsed_models)
    assert len(graph["relationships"]) == 1
    rel = graph["relationships"][0]
    assert rel["target_table"] == "dwh.dim_date"
    assert rel["target_table_type"] == "dim"


def test_declared_dimension_uses_registry_and_grain_syntax():
    """conformed_dimension maps date.month to physical dim_month; overrides hierarchy on dim_date."""
    parsed_models = {
        "dwh.dim_date": _model(
            "dim",
            schema=[
                {"name": "month_id", "datatype": "string", "tests": ["primary_key"]},
            ],
            hierarchy={
                "levels": [
                    {"level_number": 1, "name": "Month", "primary_key": "month_id"},
                ]
            },
        ),
        "dwh.dim_month": _model(
            "dim",
            schema=[
                {"name": "month_id", "datatype": "string", "tests": ["primary_key"]},
            ],
            conformed_dimension={"logical": "date", "level": "month"},
        ),
        "dwh.fct_agg": _model(
            "fact",
            schema=[
                {"name": "month_id", "datatype": "string", "dimension": "date.month"},
            ],
        ),
    }
    registry = build_dimension_registry_from_models(parsed_models)
    assert registry["date.month"] == "dwh.dim_month"
    graph = DimensionalRelationshipGraphBuilder(include_lookup=True).build_graph(
        parsed_models,
        dimension_registry=registry,
    )
    assert len(graph["relationships"]) == 1
    rel = graph["relationships"][0]
    assert rel["target_table"] == "dwh.dim_month"
    assert rel["target_column"] == "month_id"
    assert rel["origin"] == "declared_dimension"


def test_dedupes_same_relationship_declared_and_inferred():
    parsed_models = {
        "dwh.dim_customer": _model(
            "dim",
            schema=[{"name": "customer_id", "datatype": "string", "tests": ["primary_key"]}],
        ),
        "dwh.fct_sales": _model(
            "fact",
            schema=[
                {
                    "name": "customer_id",
                    "datatype": "string",
                    "fk_to": {"table": "dwh.dim_customer", "column": "customer_id"},
                },
                {
                    "name": "customer_id",
                    "datatype": "string",
                },
            ],
        ),
    }

    graph = DimensionalRelationshipGraphBuilder(infer_from_column_names=True).build_graph(
        parsed_models
    )
    rels = [
        r
        for r in graph["relationships"]
        if r["source_fact"] == "dwh.fct_sales"
        and r["target_table"] == "dwh.dim_customer"
        and r["fact_column"] == "customer_id"
        and r["target_column"] == "customer_id"
    ]
    assert len(rels) == 1
