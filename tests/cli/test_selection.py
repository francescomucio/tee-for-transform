"""
Unit tests for ModelSelector.
"""

import pytest

from tee.cli.selection import ModelSelector


class TestModelSelector:
    """Test cases for ModelSelector."""

    @pytest.fixture
    def sample_models(self):
        """Create sample parsed models for testing."""
        return {
            "schema1.model1": {"model_metadata": {"metadata": {"tags": ["nightly", "analytics"]}}},
            "schema1.model2": {"model_metadata": {"metadata": {"tags": ["daily", "analytics"]}}},
            "schema2.model3": {"model_metadata": {"metadata": {"tags": ["nightly"]}}},
            "schema2.model4": {"model_metadata": {"metadata": {}}},
            "model5": {"model_metadata": {"metadata": {}}},
        }

    def test_no_selection_selects_all(self, sample_models):
        """Test that without selection patterns, all models are selected."""
        selector = ModelSelector()

        for model_name, model_data in sample_models.items():
            assert selector.is_selected(model_name, model_data) is True

    def test_select_by_exact_name(self, sample_models):
        """Test selecting models by exact name."""
        selector = ModelSelector(select_patterns=["schema1.model1"])

        assert selector.is_selected("schema1.model1", sample_models["schema1.model1"]) is True
        assert selector.is_selected("schema1.model2", sample_models["schema1.model2"]) is False
        assert selector.is_selected("schema2.model3", sample_models["schema2.model3"]) is False

    def test_select_by_wildcard_pattern(self, sample_models):
        """Test selecting models using wildcard patterns."""
        selector = ModelSelector(select_patterns=["schema1.*"])

        assert selector.is_selected("schema1.model1", sample_models["schema1.model1"]) is True
        assert selector.is_selected("schema1.model2", sample_models["schema1.model2"]) is True
        assert selector.is_selected("schema2.model3", sample_models["schema2.model3"]) is False

    def test_select_by_table_name_only(self, sample_models):
        """Test selecting by table name only (without schema)."""
        selector = ModelSelector(select_patterns=["model1"])

        assert selector.is_selected("schema1.model1", sample_models["schema1.model1"]) is True
        assert (
            selector.is_selected("schema2.model1", sample_models["schema1.model1"]) is True
        )  # Would match if existed
        assert selector.is_selected("schema1.model2", sample_models["schema1.model2"]) is False

    def test_select_by_tag(self, sample_models):
        """Test selecting models by tag."""
        selector = ModelSelector(select_patterns=["tag:nightly"])

        assert selector.is_selected("schema1.model1", sample_models["schema1.model1"]) is True
        assert selector.is_selected("schema1.model2", sample_models["schema1.model2"]) is False
        assert selector.is_selected("schema2.model3", sample_models["schema2.model3"]) is True
        assert selector.is_selected("schema2.model4", sample_models["schema2.model4"]) is False

    def test_select_multiple_tags(self, sample_models):
        """Test selecting models with multiple tag patterns."""
        selector = ModelSelector(select_patterns=["tag:nightly", "tag:daily"])

        assert (
            selector.is_selected("schema1.model1", sample_models["schema1.model1"]) is True
        )  # Has nightly
        assert (
            selector.is_selected("schema1.model2", sample_models["schema1.model2"]) is True
        )  # Has daily
        assert (
            selector.is_selected("schema2.model3", sample_models["schema2.model3"]) is True
        )  # Has nightly
        assert selector.is_selected("schema2.model4", sample_models["schema2.model4"]) is False

    def test_exclude_by_name(self, sample_models):
        """Test excluding models by name."""
        selector = ModelSelector(exclude_patterns=["schema1.model1"])

        assert selector.is_selected("schema1.model1", sample_models["schema1.model1"]) is False
        assert selector.is_selected("schema1.model2", sample_models["schema1.model2"]) is True
        assert selector.is_selected("schema2.model3", sample_models["schema2.model3"]) is True

    def test_exclude_by_tag(self, sample_models):
        """Test excluding models by tag."""
        selector = ModelSelector(exclude_patterns=["tag:nightly"])

        assert selector.is_selected("schema1.model1", sample_models["schema1.model1"]) is False
        assert selector.is_selected("schema1.model2", sample_models["schema1.model2"]) is True
        assert selector.is_selected("schema2.model3", sample_models["schema2.model3"]) is False

    def test_select_and_exclude(self, sample_models):
        """Test combining select and exclude patterns."""
        selector = ModelSelector(select_patterns=["schema1.*"], exclude_patterns=["tag:nightly"])

        # schema1.model1 has tag:nightly, so excluded
        assert selector.is_selected("schema1.model1", sample_models["schema1.model1"]) is False
        # schema1.model2 matches schema1.* but doesn't have tag:nightly, so included
        assert selector.is_selected("schema1.model2", sample_models["schema1.model2"]) is True
        # schema2.model3 doesn't match schema1.*, so excluded
        assert selector.is_selected("schema2.model3", sample_models["schema2.model3"]) is False

    def test_select_tag_exclude_name(self, sample_models):
        """Test selecting by tag and excluding by name."""
        selector = ModelSelector(select_patterns=["tag:analytics"], exclude_patterns=["model2"])

        # schema1.model1 has analytics tag and not model2, so included
        assert selector.is_selected("schema1.model1", sample_models["schema1.model1"]) is True
        # schema1.model2 has analytics but is named model2, so excluded
        assert selector.is_selected("schema1.model2", sample_models["schema1.model2"]) is False

    def test_filter_models(self, sample_models):
        """Test filtering a dictionary of models."""
        selector = ModelSelector(select_patterns=["tag:nightly"])
        execution_order = ["schema1.model1", "schema1.model2", "schema2.model3", "schema2.model4"]

        filtered_models, filtered_order = selector.filter_models(sample_models, execution_order)

        assert len(filtered_models) == 2
        assert "schema1.model1" in filtered_models
        assert "schema2.model3" in filtered_models
        assert "schema1.model2" not in filtered_models
        assert "schema2.model4" not in filtered_models

        assert filtered_order == ["schema1.model1", "schema2.model3"]

    def test_filter_models_empty_execution_order(self, sample_models):
        """Test filtering when execution order is None."""
        selector = ModelSelector(select_patterns=["tag:nightly"])

        filtered_models, filtered_order = selector.filter_models(sample_models, None)

        assert len(filtered_models) == 2
        assert len(filtered_order) == 0  # No execution order provided

    def test_case_insensitive_name_matching(self, sample_models):
        """Test that name matching is case-insensitive."""
        selector = ModelSelector(select_patterns=["SCHEMA1.MODEL1"])

        assert selector.is_selected("schema1.model1", sample_models["schema1.model1"]) is True

    def test_case_insensitive_tag_matching(self, sample_models):
        """Test that tag matching is case-insensitive."""
        selector = ModelSelector(select_patterns=["tag:NIGHTLY"])

        assert selector.is_selected("schema1.model1", sample_models["schema1.model1"]) is True

    def test_model_without_tags(self, sample_models):
        """Test selecting models that don't have tags."""
        selector = ModelSelector(select_patterns=["tag:nightly"])

        # model5 has no tags
        assert selector.is_selected("model5", sample_models["model5"]) is False

    def test_model_without_metadata(self):
        """Test handling models without metadata."""
        selector = ModelSelector(select_patterns=["tag:nightly"])
        model_without_metadata = {"model_metadata": {}}

        # Should not crash, just return False
        assert selector.is_selected("test.model", model_without_metadata) is False

    def test_wildcard_matching(self, sample_models):
        """Test various wildcard patterns."""
        # Test * wildcard
        selector1 = ModelSelector(select_patterns=["schema*"])
        assert selector1.is_selected("schema1.model1", sample_models["schema1.model1"]) is True
        assert selector1.is_selected("schema2.model3", sample_models["schema2.model3"]) is True

        # Test ? wildcard
        selector2 = ModelSelector(select_patterns=["model?"])
        assert selector2.is_selected("schema1.model1", sample_models["schema1.model1"]) is True
        assert selector2.is_selected("model5", sample_models["model5"]) is True

    def test_multiple_select_patterns(self, sample_models):
        """Test selecting with multiple patterns (OR logic)."""
        selector = ModelSelector(select_patterns=["schema1.model1", "tag:daily"])

        # Matches schema1.model1 (by name)
        assert selector.is_selected("schema1.model1", sample_models["schema1.model1"]) is True
        # Matches schema1.model2 (by tag:daily)
        assert selector.is_selected("schema1.model2", sample_models["schema1.model2"]) is True
        # Doesn't match either pattern
        assert selector.is_selected("schema2.model3", sample_models["schema2.model3"]) is False

    def test_multiple_exclude_patterns(self, sample_models):
        """Test excluding with multiple patterns (OR logic)."""
        selector = ModelSelector(exclude_patterns=["tag:nightly", "model4"])

        # Excluded by tag:nightly
        assert selector.is_selected("schema1.model1", sample_models["schema1.model1"]) is False
        # Excluded by name model4
        assert selector.is_selected("schema2.model4", sample_models["schema2.model4"]) is False
        # Not excluded
        assert selector.is_selected("schema1.model2", sample_models["schema1.model2"]) is True
