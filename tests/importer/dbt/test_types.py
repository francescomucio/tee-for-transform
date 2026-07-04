"""
Coverage tests for dbt importer TypedDict definitions.
"""

from t4t.importer.dbt import types


def test_typed_dict_shapes_are_instantiable() -> None:
    """Ensure all TypedDict aliases can be used as runtime dict shapes."""
    log_entry: types.ConversionLogEntry = {
        "model": "my_model",
        "status": "converted",
        "warnings": [],
    }
    conversion_results: types.ConversionResults = {
        "converted": 1,
        "python_models": 0,
        "errors": 0,
        "total": 1,
        "conversion_log": [log_entry],
    }
    macro_results: types.MacroResults = {
        "converted": 1,
        "unconvertible": 0,
        "total": 1,
        "conversion_log": [log_entry],
    }
    test_results: types.TestResults = {
        "converted": 1,
        "skipped": 0,
        "errors": 0,
        "total": 1,
        "conversion_log": [log_entry],
    }
    seed_results: types.SeedResults = {"copied": 2, "errors": 0}
    variable_info: types.VariableInfo = {
        "default_value": "prod",
        "defined_in": "dbt_project.yml",
        "used_in": ["model_a"],
    }
    variables_info: types.VariablesInfo = {"variables": {"env": variable_info}}
    model_metadata: types.ModelMetadata = {
        "description": "desc",
        "materialization": "table",
        "schema": [{"name": "id"}],
        "incremental": {"strategy": "merge"},
        "tags": ["core"],
        "meta": {"owner": "data"},
        "variables": ["env"],
        "dependencies": ["stg_a"],
    }

    assert conversion_results["total"] == 1
    assert macro_results["converted"] == 1
    assert test_results["errors"] == 0
    assert seed_results["copied"] == 2
    assert variables_info["variables"]["env"]["defined_in"] == "dbt_project.yml"
    assert model_metadata["materialization"] == "table"
