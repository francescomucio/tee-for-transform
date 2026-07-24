"""Unit tests for #14 steps 1-3: OR-of-AND-groups restructuring.

- Step 1: split each `--select` value on comma into an AND-group; repeated
  `--select` values OR across groups. Regression: no-comma, single-token
  behavior (pre-#14) is unchanged -- see tests/cli/test_selection.py for the
  full byte-for-byte regression suite; this file adds the *new* comma
  behavior only.
- Step 2: `definition:`/`run:`/`tag:`/plain-name atomic condition
  recognition, including inside a comma AND-group.
- Step 3: intersection evaluation -- a model matching only one of two
  comma-joined conditions is not selected.
"""

from t4t.cli.selection import (
    DefinitionChangedCondition,
    ModelSelector,
    NameCondition,
    RunFailedCondition,
    SelectionParseError,
    TagCondition,
)


def _model(tags: list[str] | None = None) -> dict:
    return {"model_metadata": {"metadata": {"tags": tags or []}}}


class TestGroupParsing:
    """Step 1: each --select value -> one AND-group; degenerate single-token
    case matches pre-#14 (one condition per group)."""

    def test_single_token_is_one_group_one_condition(self):
        selector = ModelSelector(select_patterns=["my_model"])
        assert len(selector.select_groups) == 1
        assert len(selector.select_groups[0].conditions) == 1

    def test_comma_splits_into_and_group(self):
        selector = ModelSelector(select_patterns=["definition:changed,tag:nightly"])
        assert len(selector.select_groups) == 1
        group = selector.select_groups[0]
        assert len(group.conditions) == 2

    def test_repeated_select_values_are_separate_or_groups(self):
        selector = ModelSelector(select_patterns=["a", "tag:nightly"])
        assert len(selector.select_groups) == 2


class TestAtomicConditionRecognition:
    """Step 2."""

    def test_tag_condition_type(self):
        selector = ModelSelector(select_patterns=["tag:nightly"])
        cond = selector.select_groups[0].conditions[0]
        assert isinstance(cond, TagCondition)
        assert cond.tag == "nightly"

    def test_name_condition_type(self):
        selector = ModelSelector(select_patterns=["my_model"])
        cond = selector.select_groups[0].conditions[0]
        assert isinstance(cond, NameCondition)
        assert cond.pattern == "my_model"

    def test_definition_changed_condition_type(self):
        selector = ModelSelector(select_patterns=["definition:changed"])
        cond = selector.select_groups[0].conditions[0]
        assert isinstance(cond, DefinitionChangedCondition)

    def test_run_failed_condition_type(self):
        selector = ModelSelector(select_patterns=["run:failed"])
        cond = selector.select_groups[0].conditions[0]
        assert isinstance(cond, RunFailedCondition)

    def test_comma_group_has_two_distinct_condition_types(self):
        selector = ModelSelector(select_patterns=["definition:changed,tag:nightly"])
        conditions = selector.select_groups[0].conditions
        types = {type(c) for c in conditions}
        assert types == {DefinitionChangedCondition, TagCondition}

    def test_unsupported_definition_value_raises(self):
        import pytest

        with pytest.raises(SelectionParseError):
            ModelSelector(select_patterns=["definition:bogus"])

    def test_unsupported_run_value_raises(self):
        import pytest

        with pytest.raises(SelectionParseError):
            ModelSelector(select_patterns=["run:bogus"])

    def test_data_prefix_reserved_raises(self):
        import pytest

        with pytest.raises(SelectionParseError):
            ModelSelector(select_patterns=["data:changed"])


class TestIntersectionEvaluation:
    """Step 3: a model must satisfy every condition in a comma AND-group."""

    def test_model_matching_only_one_of_two_conditions_not_selected(self):
        selector = ModelSelector(select_patterns=["tag:nightly,tag:analytics"])
        nightly_only = _model(tags=["nightly"])
        both = _model(tags=["nightly", "analytics"])
        analytics_only = _model(tags=["analytics"])

        assert selector.is_selected("m.nightly_only", nightly_only) is False
        assert selector.is_selected("m.both", both) is True
        assert selector.is_selected("m.analytics_only", analytics_only) is False

    def test_name_and_tag_intersection(self):
        selector = ModelSelector(select_patterns=["my_model,tag:nightly"])
        matches_name_only = _model(tags=[])
        matches_both = _model(tags=["nightly"])

        assert selector.is_selected("my_model", matches_name_only) is False
        assert selector.is_selected("my_model", matches_both) is True
        # Right tag, wrong name -> still not selected (AND, not OR).
        assert selector.is_selected("other_model", matches_both) is False

    def test_union_across_repeated_select_still_or(self):
        """Regression: multiple --select flags still OR (pre-#14 behavior),
        only comma-within-one-value is new AND behavior."""
        selector = ModelSelector(select_patterns=["tag:nightly", "tag:analytics"])
        nightly_only = _model(tags=["nightly"])
        analytics_only = _model(tags=["analytics"])
        neither = _model(tags=[])

        assert selector.is_selected("m1", nightly_only) is True
        assert selector.is_selected("m2", analytics_only) is True
        assert selector.is_selected("m3", neither) is False
