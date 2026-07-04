"""
Model selection utilities for filtering models by name and tags.

Supports --select and --exclude flags similar to dbt's selection syntax.
"""

from fnmatch import fnmatch
from typing import Any


class ModelSelector:
    """Selects models based on name patterns and tags."""

    def __init__(
        self, select_patterns: list[str] | None = None, exclude_patterns: list[str] | None = None
    ) -> None:
        """
        Initialize model selector.

        Args:
            select_patterns: List of selection patterns (e.g., ["my_model", "tag:nightly"])
            exclude_patterns: List of exclusion patterns (e.g., ["deprecated", "tag:test"])
        """
        self.select_patterns = select_patterns or []
        self.exclude_patterns = exclude_patterns or []

        # Parse patterns into name patterns and tag patterns
        self.select_names: list[str] = []
        self.select_tags: list[str] = []
        self.exclude_names: list[str] = []
        self.exclude_tags: list[str] = []

        self._parse_patterns()

    def _parse_patterns(self) -> None:
        """Parse selection and exclusion patterns into name and tag categories."""
        # Parse select patterns
        for pattern in self.select_patterns:
            if pattern.startswith("tag:"):
                tag = pattern[4:]  # Remove "tag:" prefix
                self.select_tags.append(tag)
            else:
                self.select_names.append(pattern)

        # Parse exclude patterns
        for pattern in self.exclude_patterns:
            if pattern.startswith("tag:"):
                tag = pattern[4:]  # Remove "tag:" prefix
                self.exclude_tags.append(tag)
            else:
                self.exclude_names.append(pattern)

    def _matches_name(self, model_name: str, patterns: list[str]) -> bool:
        """
        Check if model name matches any of the patterns.

        Supports exact match and wildcard patterns (*, ?).

        Args:
            model_name: Full table name (e.g., "schema.table")
            patterns: List of patterns to match against

        Returns:
            True if model_name matches any pattern
        """
        if not patterns:
            return False

        for pattern in patterns:
            # Support wildcard matching
            if fnmatch(model_name, pattern) or fnmatch(model_name.lower(), pattern.lower()):
                return True
            # Also support partial matches (e.g., "schema.table" matches "table")
            parts = model_name.split(".")
            if len(parts) > 1:
                # Check if pattern matches just the table name part
                if fnmatch(parts[-1], pattern) or fnmatch(parts[-1].lower(), pattern.lower()):
                    return True
            # Exact match
            if model_name == pattern or model_name.lower() == pattern.lower():
                return True

        return False

    def _has_tag(self, model_data: dict[str, Any], tag: str) -> bool:
        """
        Check if model has the specified tag.

        Tags are stored in model_metadata.metadata.tags

        Args:
            model_data: Parsed model data
            tag: Tag to check for

        Returns:
            True if model has the tag
        """
        try:
            metadata = model_data.get("model_metadata", {})
            tags = metadata.get("metadata", {}).get("tags", [])

            if not tags:
                return False

            # Check if tag is in the list (case-insensitive)
            return any(t.lower() == tag.lower() for t in tags)
        except (AttributeError, TypeError):
            return False

    def _matches_tags(self, model_data: dict[str, Any], tags: list[str]) -> bool:
        """
        Check if model matches any of the specified tags.

        Args:
            model_data: Parsed model data
            tags: List of tags to check for

        Returns:
            True if model has any of the tags
        """
        if not tags:
            return False

        for tag in tags:
            if self._has_tag(model_data, tag):
                return True

        return False

    def is_selected(self, model_name: str, model_data: dict[str, Any]) -> bool:
        """
        Determine if a model should be selected based on selection and exclusion criteria.

        Selection logic:
        1. If no select patterns, all models are selected (unless excluded)
        2. Model must match at least one select pattern (name or tag)
        3. Model must not match any exclude pattern (name or tag)

        Args:
            model_name: Full table name (e.g., "schema.table")
            model_data: Parsed model data

        Returns:
            True if model should be included, False otherwise
        """
        # If no select patterns, all models are selected by default
        if not self.select_patterns:
            # Only check exclusion
            if self.exclude_patterns:
                return not self._is_excluded(model_name, model_data)
            return True

        # Check if model matches selection criteria
        matches_select = False

        # Check name patterns
        if self.select_names:
            matches_select = matches_select or self._matches_name(model_name, self.select_names)

        # Check tag patterns
        if self.select_tags:
            matches_select = matches_select or self._matches_tags(model_data, self.select_tags)

        if not matches_select:
            return False

        # Check exclusion
        if self.exclude_patterns:
            return not self._is_excluded(model_name, model_data)

        return True

    def _is_excluded(self, model_name: str, model_data: dict[str, Any]) -> bool:
        """
        Check if model matches exclusion criteria.

        Args:
            model_name: Full table name
            model_data: Parsed model data

        Returns:
            True if model should be excluded
        """
        # Check name exclusion
        if self.exclude_names:
            if self._matches_name(model_name, self.exclude_names):
                return True

        # Check tag exclusion
        if self.exclude_tags:
            if self._matches_tags(model_data, self.exclude_tags):
                return True

        return False

    def filter_models(
        self, parsed_models: dict[str, Any], execution_order: list[str] | None = None
    ) -> tuple[dict[str, Any], list[str]]:
        """
        Filter parsed models and execution order based on selection criteria.

        Args:
            parsed_models: Dictionary of all parsed models
            execution_order: Optional list of model names in execution order

        Returns:
            Tuple of (filtered_models, filtered_execution_order)
        """
        filtered_models = {}
        filtered_order = []

        # Filter models
        for model_name, model_data in parsed_models.items():
            if self.is_selected(model_name, model_data):
                filtered_models[model_name] = model_data

        # Filter execution order
        if execution_order:
            for model_name in execution_order:
                if model_name in filtered_models:
                    filtered_order.append(model_name)

        return filtered_models, filtered_order
