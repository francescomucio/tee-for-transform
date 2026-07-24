"""Unit tests for #14 step 7: graph modifiers (leading/trailing `+`).

Fixture DAG throughout: A -> B -> C (A is upstream of B, B is upstream of
C). Modifiers are stripped from the *whole* --select value before the
comma-split and applied to the group's evaluated result -- never to an
individual comma-separated token (see t4t/cli/selection.py's module
docstring and the issue's "Design decisions").
"""

from t4t.cli.selection import ModelSelector


def _graph() -> dict:
    return {
        "execution_order": ["s.a", "s.b", "s.c"],
        "dependencies": {"s.a": [], "s.b": ["s.a"], "s.c": ["s.b"]},
        "dependents": {"s.a": ["s.b"], "s.b": ["s.c"], "s.c": []},
    }


def _models(tags: dict[str, list[str]] | None = None) -> dict:
    tags = tags or {}
    return {
        name: {"model_metadata": {"metadata": {"tags": tags.get(name, [])}}}
        for name in ("s.a", "s.b", "s.c")
    }


class TestNameBasedModifiers:
    def test_trailing_plus_expands_downstream(self):
        selector = ModelSelector(select_patterns=["s.a+"])
        filtered, _ = selector.filter_models(_models(), graph=_graph())
        assert set(filtered.keys()) == {"s.a", "s.b", "s.c"}

    def test_leading_plus_expands_upstream(self):
        selector = ModelSelector(select_patterns=["+s.c"])
        filtered, _ = selector.filter_models(_models(), graph=_graph())
        assert set(filtered.keys()) == {"s.a", "s.b", "s.c"}

    def test_middle_node_downstream_only(self):
        selector = ModelSelector(select_patterns=["s.b+"])
        filtered, _ = selector.filter_models(_models(), graph=_graph())
        assert set(filtered.keys()) == {"s.b", "s.c"}
        assert "s.a" not in filtered

    def test_no_modifier_is_exact_match_only(self):
        selector = ModelSelector(select_patterns=["s.b"])
        filtered, _ = selector.filter_models(_models(), graph=_graph())
        assert set(filtered.keys()) == {"s.b"}

    def test_both_modifiers_together(self):
        selector = ModelSelector(select_patterns=["+s.b+"])
        filtered, _ = selector.filter_models(_models(), graph=_graph())
        assert set(filtered.keys()) == {"s.a", "s.b", "s.c"}


class TestTagBasedModifierWithIntersection:
    """`"definition:changed,tag:nightly+"` style: modifier wraps the whole
    comma-AND-group's result, not an individual token."""

    def test_intersection_then_downstream_expansion(self):
        # Only s.a is tagged nightly; select "tag:nightly+" -> {s.a} then
        # downstream expand to include s.b, s.c.
        models = _models(tags={"s.a": ["nightly"]})
        selector = ModelSelector(select_patterns=["tag:nightly+"])
        filtered, _ = selector.filter_models(models, graph=_graph())
        assert set(filtered.keys()) == {"s.a", "s.b", "s.c"}

    def test_intersection_group_base_set_before_expansion(self):
        # s.b and s.c both tagged nightly, but only s.c matches
        # "tag:nightly,tag:other" (AND) -> base={s.c}, then + expands
        # nothing further downstream of s.c (leaf).
        models = _models(tags={"s.b": ["nightly"], "s.c": ["nightly", "other"]})
        selector = ModelSelector(select_patterns=["tag:nightly,tag:other+"])
        filtered, _ = selector.filter_models(models, graph=_graph())
        assert set(filtered.keys()) == {"s.c"}


class TestModifiersRequireGraph:
    def test_modifier_without_graph_raises(self):
        from t4t.cli.selection import SelectionContextError

        selector = ModelSelector(select_patterns=["s.a+"])
        import pytest

        with pytest.raises(SelectionContextError):
            selector.filter_models(_models())  # no graph= passed


class TestExcludeWithModifiers:
    def test_exclude_downstream_of_a_removes_b_and_c(self):
        selector = ModelSelector(select_patterns=None, exclude_patterns=["s.a+"])
        filtered, _ = selector.filter_models(_models(), graph=_graph())
        assert set(filtered.keys()) == set()
