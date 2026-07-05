"""Run manifest conversion and round-trip."""

from tee.state.manifest import (
    SCHEMA_VERSION,
    manifest_from_dict,
    manifest_to_dict,
    results_to_manifest,
    utc_now_iso,
)


def test_results_to_manifest_run_shape_round_trip():
    graph = {
        "nodes": ["a.b", "a.c"],
        "dependencies": {"a.b": [], "a.c": ["a.b"]},
        "dependents": {"a.b": ["a.c"], "a.c": []},
    }
    results = {
        "executed_tables": ["a.b"],
        "failed_tables": [{"table": "a.c", "error": "boom"}],
        "executed_functions": [],
        "failed_functions": [],
        "table_info": {"a.b": {"row_count": 1}},
        "analysis": {
            "execution_order": ["a.b", "a.c"],
            "dependency_graph": graph,
        },
    }
    t0 = utc_now_iso()
    t1 = utc_now_iso()
    m = results_to_manifest(
        results,
        "run",
        "/tmp/proj",
        t0,
        t1,
        project_config={"x": 1},
        variables={"y": 2},
        function_names=set(),
    )
    assert m.schema_version == SCHEMA_VERSION
    assert m.command == "run"
    assert m.execution_order == ["a.b", "a.c"]
    names = {n.name: n for n in m.nodes}
    assert names["a.b"].status == "success"
    assert names["a.c"].status == "failed"
    d = manifest_to_dict(m)
    m2 = manifest_from_dict(d)
    assert m2.run_id == m.run_id
    assert [n.name for n in m2.nodes] == [n.name for n in m.nodes]


def test_results_to_manifest_build_skipped_dict():
    graph = {
        "nodes": ["m1", "m2"],
        "dependencies": {"m1": [], "m2": ["m1"]},
        "dependents": {"m1": ["m2"], "m2": []},
    }
    results = {
        "executed_tables": [],
        "failed_tables": [{"table": "m1", "error": "x"}],
        "skipped_tables": [{"table": "m2", "reason": "upstream_failed:m1"}],
        "executed_functions": [],
        "failed_functions": [],
        "table_info": {},
        "analysis": {
            "execution_order": ["m1", "m2"],
            "dependency_graph": graph,
        },
    }
    t0 = utc_now_iso()
    t1 = utc_now_iso()
    m = results_to_manifest(results, "build", "/p", t0, t1, function_names=set())
    names = {n.name: n for n in m.nodes}
    assert names["m1"].status == "failed"
    assert names["m2"].status == "skipped"
    assert names["m2"].skip_reason == "upstream_failed:m1"
