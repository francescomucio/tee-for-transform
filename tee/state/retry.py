"""
Compute which models to re-run from a stored manifest (failed + downstream + upstream-skipped).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from tee.compiler import compile_project
from tee.executor_helpers.shared_helpers import validate_compile_results
from tee.state.backend import LocalStateBackend
from tee.state.manifest import SCHEMA_VERSION, RunManifest

logger = logging.getLogger(__name__)

_UPSTREAM_SKIP_PREFIXES = (
    "upstream_failed:",
    "not_run:downstream_of_failure",
    "depends_on_failed",
)


def _is_upstream_skip(reason: str | None) -> bool:
    if not reason:
        return False
    if reason == "depends_on_failed":
        return True
    return any(reason.startswith(p) for p in _UPSTREAM_SKIP_PREFIXES)


def _transitive_downstream(graph: dict[str, Any], seeds: set[str]) -> set[str]:
    dependents: dict[str, list[str]] = graph.get("dependents") or {}
    out: set[str] = set()
    visited = set(seeds)
    stack = list(seeds)
    while stack:
        n = stack.pop()
        for d in dependents.get(n, []):
            if d.startswith("test:"):
                continue
            if d in visited:
                continue
            visited.add(d)
            out.add(d)
            stack.append(d)
    return out


def compute_retry_set(manifest: RunManifest, graph: dict[str, Any]) -> set[str]:
    """
    Models to retry: failed nodes, skipped-because-upstream, and all transitive dependents.

    Names not present in the current graph are dropped (with a warning).
    """
    graph_nodes: set[str] = set(graph.get("nodes") or [])
    if not graph_nodes and graph.get("dependencies"):
        graph_nodes = set(graph["dependencies"].keys())

    failed: set[str] = set()
    upstream_skipped: set[str] = set()
    for node in manifest.nodes:
        if node.name.startswith("test:"):
            continue
        if node.status == "failed":
            failed.add(node.name)
        elif node.status == "skipped" and _is_upstream_skip(node.skip_reason):
            upstream_skipped.add(node.name)

    seeds = failed | upstream_skipped
    downstream = _transitive_downstream(graph, seeds)
    raw = seeds | downstream

    valid: set[str] = set()
    for name in raw:
        if name in graph_nodes:
            valid.add(name)
        else:
            logger.warning(
                "Retry: manifest model %r not in current graph (skipped)",
                name,
            )
    return valid


def prepare_retry_select_patterns(
    project_folder: str,
    connection_config: dict[str, Any],
    variables: dict[str, Any] | None,
    project_config: dict[str, Any] | None,
) -> list[str]:
    """
    Compile the project, load the latest manifest, return model names to pass as --select patterns.

    Raises:
        ValueError: with a user-facing message when retry cannot proceed
    """
    compile_results = compile_project(
        project_folder=project_folder,
        connection_config=connection_config,
        variables=variables,
        project_config=project_config,
    )
    graph, _, _ = validate_compile_results(compile_results)
    backend = LocalStateBackend(Path(project_folder) / "output")
    manifest = backend.read_latest()
    if manifest is None:
        raise ValueError(
            "No previous run manifest found under output/. Run `t4t run` or `t4t build` first."
        )
    if manifest.schema_version != SCHEMA_VERSION:
        raise ValueError(
            f"Stored run manifest uses schema version {manifest.schema_version}; "
            f"this t4t expects {SCHEMA_VERSION}. Delete output/last_run.json or upgrade t4t."
        )
    retry_set = compute_retry_set(manifest, graph)
    if not retry_set:
        raise ValueError(
            "Nothing to retry: the last run had no failed models or downstream-skipped models."
        )
    return sorted(retry_set)
