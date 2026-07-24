"""
Model selection utilities for filtering models by name, tags, definition
change, and last-run status.

Supports `--select`/`--exclude` (dbt-compatible selection syntax):

- **Union (OR)**: repeated `--select` flags OR together -- a model is
  selected if it matches *any* one of them.
- **Intersection (AND)**: comma-separated tokens *within one* `--select`
  value (no spaces) AND together -- a model must satisfy *every* token to
  be selected via that value.
- **Graph modifiers**: a leading `+` (e.g. `+my_model`) expands to also
  include everything the match set depends on (upstream); a trailing `+`
  (e.g. `my_model+`) expands to also include everything that depends on the
  match set (downstream). Modifiers are stripped from the *whole*
  `--select` value before the comma-split and apply to the group's result
  as a whole, never to an individual comma-separated token.

Parsing model (disjunctive normal form -- OR of AND-groups): each
`--select`/`--exclude` value is one AND-group of atomic conditions
(comma-separated, no spaces); the list of repeated flags is OR'd across
groups. A single bare pattern (no comma) is the degenerate one-condition
group -- today's pre-#14 behavior, unchanged.

Atomic conditions (interchangeable inside any AND-group):

- Plain name pattern (glob, e.g. `stg_orders`, `staging_*`).
- `tag:<tag>` -- model carries this tag.
- `definition:changed` -- model's current fingerprint differs from the
  stored baseline (#13's fingerprint storage; see
  ``docs/user-guide/fingerprinting.md`` and
  ``docs/user-guide/selection.md``). Requires a `StateBackend` and the
  project's dependency graph -- see `ModelSelector.filter_models`.
- `run:failed` -- model has `status == "failed"` in the last persisted run
  manifest (#18). Requires a `StateBackend`.

`data:*` is a reserved prefix for #19 (not implemented yet) and raises a
clear error rather than being silently treated as a name pattern.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from fnmatch import fnmatch
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from t4t.state.backend import StateBackend

logger = logging.getLogger(__name__)

_TEST_NODE_PREFIX = "test:"

# Namespace prefixes reserved for virtual selectors -- model names should
# not rely on these prefixes (same caveat that already applied to `tag:`).
_DEFINITION_PREFIX = "definition:"
_RUN_PREFIX = "run:"
_DATA_PREFIX = "data:"  # reserved for #19, not implemented


class SelectionError(ValueError):
    """Base class for `--select`/`--exclude` errors surfaced to the CLI.

    Subclasses `ValueError` so existing `except ValueError` / catch-all
    `except Exception` handling in the CLI commands (`run.py`/`build.py`)
    already reports these as clean user-facing errors without extra wiring.
    """


class SelectionParseError(SelectionError):
    """A `--select`/`--exclude` value could not be parsed."""


class SelectionContextError(SelectionError):
    """A parsed selector needs data (a `StateBackend`, a dependency graph)
    that wasn't provided -- e.g. `definition:changed` without a
    `state_backend`, or a graph modifier (`+`) without a `graph`."""


# --------------------------------------------------------------------------
# Atomic conditions
# --------------------------------------------------------------------------


class _SelectionContext:
    """Precomputed, per-`ModelSelector` data that atomic conditions read.

    Built once (see `ModelSelector.prepare`) from a `StateBackend` +
    dependency graph + the full set of parsed models -- never recomputed
    per model.
    """

    def __init__(
        self,
        changed_set: set[str] | None = None,
        failed_set: set[str] | None = None,
    ) -> None:
        self.changed_set = changed_set
        self.failed_set = failed_set


class Condition(Protocol):
    """An atomic, composable selection condition."""

    def matches(
        self, model_name: str, model_data: dict[str, Any], ctx: _SelectionContext | None
    ) -> bool: ...


def _name_matches(model_name: str, pattern: str) -> bool:
    """Match a single model name against a single glob pattern.

    Same semantics as pre-#14's `_matches_name`, applied to one pattern at
    a time: full-name match, last-dot-segment match (so `--select
    my_table` matches `schema.my_table`), and case-insensitive fallback for
    both, all supporting `fnmatch`-style wildcards.
    """
    if fnmatch(model_name, pattern) or fnmatch(model_name.lower(), pattern.lower()):
        return True
    parts = model_name.split(".")
    if len(parts) > 1 and (
        fnmatch(parts[-1], pattern) or fnmatch(parts[-1].lower(), pattern.lower())
    ):
        return True
    return model_name == pattern or model_name.lower() == pattern.lower()


def _has_tag(model_data: dict[str, Any], tag: str) -> bool:
    """Check if model has the specified tag (case-insensitive)."""
    try:
        metadata = model_data.get("model_metadata", {})
        tags = metadata.get("metadata", {}).get("tags", [])
        if not tags:
            return False
        return any(t.lower() == tag.lower() for t in tags)
    except (AttributeError, TypeError):
        return False


@dataclass(frozen=True)
class NameCondition:
    """Plain name-pattern atomic condition (glob, exact, or table-only)."""

    pattern: str

    def matches(
        self, model_name: str, _model_data: dict[str, Any], _ctx: _SelectionContext | None
    ) -> bool:
        return _name_matches(model_name, self.pattern)


@dataclass(frozen=True)
class TagCondition:
    """`tag:<tag>` atomic condition."""

    tag: str

    def matches(
        self, _model_name: str, model_data: dict[str, Any], _ctx: _SelectionContext | None
    ) -> bool:
        return _has_tag(model_data, self.tag)


@dataclass(frozen=True)
class DefinitionChangedCondition:
    """`definition:changed` atomic condition (#13 fingerprint diff vs baseline)."""

    def matches(
        self, model_name: str, _model_data: dict[str, Any], ctx: _SelectionContext | None
    ) -> bool:
        if ctx is None or ctx.changed_set is None:
            raise SelectionContextError(
                "'definition:changed' requires a StateBackend and dependency graph "
                "(pass state_backend/graph to ModelSelector.filter_models())."
            )
        return model_name in ctx.changed_set


@dataclass(frozen=True)
class RunFailedCondition:
    """`run:failed` atomic condition (#18 last persisted run manifest)."""

    def matches(
        self, model_name: str, _model_data: dict[str, Any], ctx: _SelectionContext | None
    ) -> bool:
        if ctx is None or ctx.failed_set is None:
            raise SelectionContextError(
                "'run:failed' requires a StateBackend "
                "(pass state_backend to ModelSelector.filter_models())."
            )
        return model_name in ctx.failed_set


# --------------------------------------------------------------------------
# Parsing: modifiers, comma AND-groups, atomic conditions
# --------------------------------------------------------------------------


@dataclass
class SelectGroup:
    """One AND-group parsed from a single `--select`/`--exclude` value."""

    conditions: list[Condition]
    upstream: bool = False
    downstream: bool = False
    raw: str = ""

    @property
    def has_modifier(self) -> bool:
        return self.upstream or self.downstream


def _strip_modifiers(value: str) -> tuple[str, bool, bool]:
    """Strip a leading `+` (upstream) and/or trailing `+` (downstream) off
    the *whole* selector value, before any comma-split. Returns (remainder,
    upstream, downstream)."""
    upstream = False
    downstream = False
    remainder = value
    if remainder.startswith("+"):
        upstream = True
        remainder = remainder[1:]
    if remainder.endswith("+"):
        downstream = True
        remainder = remainder[:-1]
    return remainder, upstream, downstream


def _parse_atomic_condition(token: str) -> Condition:
    if token.startswith("tag:"):
        return TagCondition(token[len("tag:") :])
    if token.startswith(_DEFINITION_PREFIX):
        value = token[len(_DEFINITION_PREFIX) :]
        if value != "changed":
            raise SelectionParseError(
                f"Unsupported selector {token!r}: only 'definition:changed' is implemented."
            )
        return DefinitionChangedCondition()
    if token.startswith(_RUN_PREFIX):
        value = token[len(_RUN_PREFIX) :]
        if value != "failed":
            raise SelectionParseError(
                f"Unsupported selector {token!r}: only 'run:failed' is implemented."
            )
        return RunFailedCondition()
    if token.startswith(_DATA_PREFIX):
        raise SelectionParseError(
            f"'data:' selectors ({token!r}) are reserved for data-state selection "
            "(#19) and not implemented yet."
        )
    return NameCondition(token)


def _parse_group(value: str) -> SelectGroup:
    remainder, upstream, downstream = _strip_modifiers(value)
    tokens = [t for t in remainder.split(",") if t]
    if not tokens:
        raise SelectionParseError(f"Empty selector: {value!r}")
    conditions = [_parse_atomic_condition(t) for t in tokens]
    return SelectGroup(conditions=conditions, upstream=upstream, downstream=downstream, raw=value)


# --------------------------------------------------------------------------
# ModelSelector
# --------------------------------------------------------------------------


class ModelSelector:
    """Selects models based on name patterns, tags, definition change, and
    last-run status, combined via dbt-compatible OR-of-AND-groups."""

    def __init__(
        self,
        select_patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
        *,
        state_backend: StateBackend | None = None,
        env_name: str | None = None,
    ) -> None:
        """
        Initialize model selector.

        Args:
            select_patterns: List of `--select` values (e.g.
                `["my_model", "tag:nightly", "definition:changed,tag:nightly+"]`).
                Repeated values OR together; comma-separated tokens *within*
                one value AND together (dbt-compatible).
            exclude_patterns: List of `--exclude` values, same syntax.
            state_backend: `StateBackend` used to resolve `definition:changed`
                and `run:failed`. Can also be supplied later via
                `filter_models(..., state_backend=...)`.
            env_name: Environment name, used only for log messages (e.g.
                "no baseline for environment 'dev'").
        """
        self.select_patterns = select_patterns or []
        self.exclude_patterns = exclude_patterns or []
        self.state_backend = state_backend
        self.env_name = env_name

        self.select_groups: list[SelectGroup] = [_parse_group(p) for p in self.select_patterns]
        self.exclude_groups: list[SelectGroup] = [_parse_group(p) for p in self.exclude_patterns]

        self._ctx: _SelectionContext | None = None
        # Populated by `prepare()` only for groups that use a graph modifier
        # (`+`) -- those need the full-project match set expanded via graph
        # traversal, which can't be evaluated per-model. Keyed by id(group).
        self._expanded: dict[int, set[str]] = {}
        self._prepared = False

    # -- preparation (data-backed conditions + graph modifiers) ----------

    def prepare(
        self,
        parsed_models: dict[str, Any],
        graph: dict[str, Any] | None = None,
        state_backend: StateBackend | None = None,
    ) -> None:
        """Resolve data-backed conditions (`definition:changed`, `run:failed`)
        and graph modifiers (`+`) against a concrete project.

        `parsed_models` must be the project's *full*, unfiltered set (graph
        modifiers expand from the true dependency graph, not from an
        already-selected subset). Safe to call more than once (e.g. if
        `filter_models` is called again); each call recomputes from
        scratch.
        """
        backend = state_backend if state_backend is not None else self.state_backend
        needs_changed = self._uses_condition(DefinitionChangedCondition)
        needs_failed = self._uses_condition(RunFailedCondition)
        needs_graph = any(g.has_modifier for g in (*self.select_groups, *self.exclude_groups))

        changed_set: set[str] | None = None
        failed_set: set[str] | None = None

        if needs_changed:
            if backend is None:
                raise SelectionContextError(
                    "'definition:changed' requires a StateBackend "
                    "(pass state_backend to ModelSelector.filter_models())."
                )
            changed_set = _compute_changed_set(parsed_models, graph or {}, backend, self.env_name)

        if needs_failed:
            if backend is None:
                raise SelectionContextError(
                    "'run:failed' requires a StateBackend "
                    "(pass state_backend to ModelSelector.filter_models())."
                )
            failed_set = _compute_failed_set(backend)

        self._ctx = _SelectionContext(changed_set=changed_set, failed_set=failed_set)

        self._expanded = {}
        if needs_graph:
            if graph is None:
                raise SelectionContextError(
                    "A graph modifier ('+') requires the project's dependency graph "
                    "(pass graph to ModelSelector.filter_models())."
                )
            universe = list(parsed_models.keys())
            for group in (*self.select_groups, *self.exclude_groups):
                if not group.has_modifier:
                    continue
                base = {
                    name
                    for name in universe
                    if all(
                        cond.matches(name, parsed_models[name], self._ctx)
                        for cond in group.conditions
                    )
                }
                expanded = set(base)
                if group.upstream:
                    from t4t.state.graph_walk import transitive_upstream

                    expanded |= transitive_upstream(graph, base)
                if group.downstream:
                    from t4t.state.graph_walk import transitive_downstream

                    expanded |= transitive_downstream(graph, base)
                self._expanded[id(group)] = expanded

        self._prepared = True

    def _uses_condition(self, condition_type: type) -> bool:
        for group in (*self.select_groups, *self.exclude_groups):
            for cond in group.conditions:
                if isinstance(cond, condition_type):
                    return True
        return False

    # -- matching ----------------------------------------------------------

    def _group_matches(
        self, group: SelectGroup, model_name: str, model_data: dict[str, Any]
    ) -> bool:
        if group.has_modifier:
            expanded = self._expanded.get(id(group))
            if expanded is None:
                raise SelectionContextError(
                    f"Selector {group.raw!r} uses a graph modifier ('+') and requires "
                    "ModelSelector.prepare()/filter_models() to be called with a "
                    "dependency graph before is_selected()."
                )
            return model_name in expanded
        return all(cond.matches(model_name, model_data, self._ctx) for cond in group.conditions)

    def _matches_any_group(
        self, groups: list[SelectGroup], model_name: str, model_data: dict[str, Any]
    ) -> bool:
        return any(self._group_matches(group, model_name, model_data) for group in groups)

    def is_selected(self, model_name: str, model_data: dict[str, Any]) -> bool:
        """
        Determine if a model should be selected based on selection and exclusion criteria.

        Selection logic:
        1. If no select patterns, all models are selected (unless excluded).
        2. Model must match at least one select group (OR across groups; a
           group matches only if the model satisfies every condition in it, AND).
        3. Model must not match any exclude group.

        Args:
            model_name: Full table name (e.g., "schema.table")
            model_data: Parsed model data

        Returns:
            True if model should be included, False otherwise
        """
        if not self.select_patterns:
            selected = True
        else:
            selected = self._matches_any_group(self.select_groups, model_name, model_data)

        if not selected:
            return False

        return not (
            self.exclude_patterns
            and self._matches_any_group(self.exclude_groups, model_name, model_data)
        )

    def filter_models(
        self,
        parsed_models: dict[str, Any],
        execution_order: list[str] | None = None,
        *,
        graph: dict[str, Any] | None = None,
        state_backend: StateBackend | None = None,
    ) -> tuple[dict[str, Any], list[str]]:
        """
        Filter parsed models and execution order based on selection criteria.

        Args:
            parsed_models: Dictionary of all parsed models. Must be the
                project's *full*, unfiltered set -- graph modifiers and
                `definition:changed`'s fingerprint chain both need the true
                project graph, not an already-narrowed one.
            execution_order: Optional list of model names in execution order
            graph: Project's dependency graph (`{"dependencies": ...,
                "dependents": ..., "execution_order": ...}`), required only
                if any selector uses a graph modifier (`+`) or
                `definition:changed` (fingerprint chain needs it too).
            state_backend: `StateBackend`, required only if any selector
                uses `definition:changed` or `run:failed`. Falls back to the
                one passed to `__init__`.

        Returns:
            Tuple of (filtered_models, filtered_execution_order)
        """
        self.prepare(parsed_models, graph=graph, state_backend=state_backend)

        filtered_models = {}
        for model_name, model_data in parsed_models.items():
            if self.is_selected(model_name, model_data):
                filtered_models[model_name] = model_data

        filtered_order = []
        if execution_order:
            for model_name in execution_order:
                if model_name in filtered_models:
                    filtered_order.append(model_name)

        return filtered_models, filtered_order


def _compute_changed_set(
    parsed_models: dict[str, Any],
    graph: dict[str, Any],
    state_backend: Any,
    env_name: str | None,
) -> set[str]:
    """Models whose current fingerprint differs from the stored baseline
    (#13), plus models with no stored baseline at all (fail-open -- treated
    as changed, per #14's "missing baseline" design decision)."""
    from t4t.engine.fingerprint import compute_project_fingerprints, read_valid_fingerprint

    current = compute_project_fingerprints(parsed_models, graph)

    changed: set[str] = set()
    missing: list[str] = []
    for name, fp in current.items():
        stored = read_valid_fingerprint(state_backend, name)
        if stored is None:
            changed.add(name)
            missing.append(name)
        elif stored.fingerprint != fp.fingerprint:
            changed.add(name)

    if missing:
        env_desc = f" (env: {env_name})" if env_name else ""
        logger.warning(
            "No baseline%s for %d model(s) -- treating as changed: %s",
            env_desc,
            len(missing),
            ", ".join(sorted(missing)),
            extra={"cli_output": True},
        )

    return changed


def _compute_failed_set(state_backend: Any) -> set[str]:
    """Model names with `status == "failed"` in the last persisted run manifest."""
    manifest = state_backend.read_latest()
    if manifest is None:
        logger.warning(
            "'run:failed' matched no models: no previous run manifest found.",
            extra={"cli_output": True},
        )
        return set()
    return {
        node.name
        for node in manifest.nodes
        if node.status == "failed" and not node.name.startswith(_TEST_NODE_PREFIX)
    }
