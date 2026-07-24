"""Generic transitive-closure walks over a project dependency graph.

Extracted so there is exactly **one** implementation of "walk the dependency
graph transitively from a set of seed models", shared by:

- `t4t.state.retry.compute_retry_set` (#18's ``--retry``: failed models +
  their transitive downstream dependents).
- `t4t.cli.selection` (#14's graph modifiers -- leading ``+`` for upstream,
  trailing ``+`` for downstream -- and, via ``--retry`` becoming sugar for
  ``--select run:failed+``, the same downstream walk as above).

Both directions use the same dependency-graph shape produced by
`ProjectParser.build_dependency_graph()` / `ParserOrchestrator
.get_execution_order()`: a dict with ``"dependencies"`` (model -> its direct
upstream deps) and ``"dependents"`` (model -> its direct downstream
dependents) keys. Test nodes (``test:``-prefixed) are never stepped into --
they aren't models, and neither `--retry` nor #14's modifiers select them.
"""

from typing import Any

_TEST_NODE_PREFIX = "test:"


def _walk(adjacency: dict[str, list[str]], seeds: set[str]) -> set[str]:
    """BFS over `adjacency` starting from `seeds`; returns reachable nodes,
    excluding the seeds themselves and any `test:`-prefixed node."""
    out: set[str] = set()
    visited = set(seeds)
    stack = list(seeds)
    while stack:
        n = stack.pop()
        for neighbor in adjacency.get(n, []):
            if neighbor.startswith(_TEST_NODE_PREFIX):
                continue
            if neighbor in visited:
                continue
            visited.add(neighbor)
            out.add(neighbor)
            stack.append(neighbor)
    return out


def transitive_downstream(graph: dict[str, Any], seeds: set[str]) -> set[str]:
    """All transitive dependents (children) of `seeds` -- i.e. everything
    that depends, directly or indirectly, on any model in `seeds`.

    Does not include the seeds themselves.
    """
    dependents: dict[str, list[str]] = graph.get("dependents") or {}
    return _walk(dependents, seeds)


def transitive_upstream(graph: dict[str, Any], seeds: set[str]) -> set[str]:
    """All transitive dependencies (ancestors) of `seeds` -- i.e. everything
    that any model in `seeds` depends on, directly or indirectly.

    Does not include the seeds themselves.
    """
    dependencies: dict[str, list[str]] = graph.get("dependencies") or {}
    return _walk(dependencies, seeds)
