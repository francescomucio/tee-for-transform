"""
Compute which models to re-run from a stored manifest (failed + downstream + upstream-skipped).

Note (#14): the CLI no longer calls `compute_retry_set` directly -- `--retry`
is now sugar for `--select run:failed+`, resolved by `t4t.cli.selection`
using the same `t4t.state.graph_walk.transitive_downstream` this module
uses below (single implementation of the graph walk, see that module's
docstring). `compute_retry_set` is kept here as a tested, standalone utility
(and because its seed set -- failed *and* upstream-skipped nodes -- is a
useful building block on its own), but production selection goes through
`ModelSelector` now.
"""

import logging
from typing import Any

from t4t.state.graph_walk import transitive_downstream
from t4t.state.manifest import RunManifest

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
    downstream = transitive_downstream(graph, seeds)
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
