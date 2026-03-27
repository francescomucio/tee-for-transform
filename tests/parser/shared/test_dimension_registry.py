"""Tests for auto-built dimension registry and shorthand resolution."""

import pytest

from tee.parser.shared.dimension_registry import (
    build_dimension_registry_from_models,
    hierarchy_level_slugs,
    is_dimension_model,
    logical_base_key,
    parse_dimension_field,
    registry_lookup_table,
    resolve_dimension_target_table,
)


def _dim_meta(table_type="dim", schema=None, hierarchy=None):
    return {
        "model_metadata": {
            "metadata": {
                "table_type": table_type,
                "schema": schema or [],
                "hierarchy": hierarchy,
            }
        }
    }


def test_build_dimension_registry_from_dim_prefix_and_hierarchy():
    parsed = {
        "dwh.dim_date": _dim_meta(
            schema=[{"name": "month_id"}],
            hierarchy={
                "levels": [
                    {"level_number": 1, "name": "Month", "primary_key": "month_id"},
                ]
            },
        ),
        "dwh.fct_sales": {"model_metadata": {"metadata": {"table_type": "fact", "schema": []}}},
    }
    reg = build_dimension_registry_from_models(parsed)
    assert reg["date"] == "dwh.dim_date"
    assert reg["date.month"] == "dwh.dim_date"


def test_build_dimension_registry_table_type_dimension_alias():
    parsed = {
        "lake.star_calendar": _dim_meta(
            table_type="dimension",
            schema=[],
        ),
    }
    reg = build_dimension_registry_from_models(parsed)
    assert reg["star_calendar"] == "lake.star_calendar"


def test_build_dimension_registry_conflict_raises():
    parsed = {
        "a.dim_date": _dim_meta(),
        "b.dim_date": _dim_meta(),
    }
    with pytest.raises(ValueError, match="Ambiguous dimension registry"):
        build_dimension_registry_from_models(parsed)


def test_parse_dimension_field_logical_and_level():
    assert parse_dimension_field("date.month") == ("date", "month")
    assert parse_dimension_field("customer") == ("customer", None)


def test_registry_lookup_table_composite_only_when_level():
    reg = {"date": "dwh.dim_date", "date.month": "dwh.dim_date"}
    assert registry_lookup_table("date", "month", reg) == ("dwh.dim_date", "date.month")
    assert registry_lookup_table("date", None, reg) == ("dwh.dim_date", "date")


def test_resolve_dimension_target_table_uses_built_registry():
    parsed = {
        "shared.dim_calendar": _dim_meta(),
    }
    reg = build_dimension_registry_from_models(parsed)
    t = resolve_dimension_target_table("dwh.fct_sales", "calendar", reg, set(parsed.keys()))
    assert t == "shared.dim_calendar"


def test_resolve_dimension_target_table_level_heuristic_prefers_existing():
    ids = {"mart.lkp_month", "mart.dim_sales"}
    t = resolve_dimension_target_table("mart.fct_agg", "date.month", {}, ids)
    assert t == "mart.lkp_month"


def test_logical_base_key():
    assert logical_base_key("dwh.dim_date") == "date"
    assert logical_base_key("lake.calendar_dim") == "calendar_dim"


def test_is_dimension_model():
    assert is_dimension_model("x.dim_y", {"table_type": "fact"}) is True
    assert is_dimension_model("lake.cal", {"table_type": "dim"}) is True
    assert is_dimension_model("lake.cal", {"table_type": "dimension"}) is True
    assert is_dimension_model("lake.fct_x", {"table_type": "fact"}) is False


def test_conformed_dimension_overrides_hierarchy_level_key():
    """Physical dim_month can claim date.month via conformed_dimension metadata."""
    parsed = {
        "dwh.dim_date": _dim_meta(
            hierarchy={
                "levels": [{"level_number": 1, "name": "Month", "primary_key": "m"}],
            },
        ),
        "dwh.dim_month": {
            "model_metadata": {
                "metadata": {
                    "table_type": "dim",
                    "schema": [],
                    "conformed_dimension": {"logical": "date", "level": "month"},
                }
            }
        },
    }
    reg = build_dimension_registry_from_models(parsed)
    assert reg["date.month"] == "dwh.dim_month"


def test_hierarchy_level_slugs():
    meta = {
        "hierarchy": {
            "levels": [
                {"name": "Year"},
                {"name": "Month"},
                {"name": "Month"},
            ]
        }
    }
    assert hierarchy_level_slugs(meta) == ["year", "month"]
