"""Retry set computation."""

import logging

from tee.state.manifest import NodeResult, RunManifest
from tee.state.retry import compute_retry_set


def _manifest(nodes: list[NodeResult]) -> RunManifest:
    return RunManifest(
        schema_version=1,
        t4t_version="0.1.0",
        run_id="r1",
        command="run",
        started_at="t0",
        finished_at="t1",
        project_root="/p",
        config_hash=None,
        vars_hash=None,
        execution_order=[n.name for n in nodes],
        nodes=nodes,
        functions=[],
    )


def test_transitive_downstream():
    graph = {
        "nodes": ["A", "B", "C"],
        "dependents": {"A": ["B"], "B": ["C"], "C": []},
        "dependencies": {"A": [], "B": ["A"], "C": ["B"]},
    }
    m = _manifest(
        [
            NodeResult(name="A", status="failed", error="e"),
            NodeResult(name="B", status="skipped", skip_reason="not_run:downstream_of_failure"),
            NodeResult(name="C", status="skipped", skip_reason="not_run:downstream_of_failure"),
        ]
    )
    s = compute_retry_set(m, graph)
    assert s == {"A", "B", "C"}


def test_graph_drift_drops_unknown_names(caplog):
    caplog.set_level(logging.WARNING)
    graph = {
        "nodes": ["A"],
        "dependents": {"A": []},
        "dependencies": {"A": []},
    }
    m = _manifest([NodeResult(name="X", status="failed", error="e")])
    s = compute_retry_set(m, graph)
    assert s == set()
    assert any("X" in r.getMessage() for r in caplog.records)


def test_no_failures_empty_set():
    graph = {
        "nodes": ["A"],
        "dependents": {"A": []},
        "dependencies": {"A": []},
    }
    m = _manifest([NodeResult(name="A", status="success", row_count=1)])
    assert compute_retry_set(m, graph) == set()


def test_upstream_skipped_build_reason():
    graph = {
        "nodes": ["A", "B"],
        "dependents": {"A": ["B"], "B": []},
        "dependencies": {"A": [], "B": ["A"]},
    }
    m = _manifest(
        [
            NodeResult(name="A", status="failed", error="e"),
            NodeResult(name="B", status="skipped", skip_reason="upstream_failed:A"),
        ]
    )
    assert compute_retry_set(m, graph) == {"A", "B"}
