"""
Model selector for dbt import.

Filters dbt models based on name patterns and tags, similar to dbt's selection syntax.
"""

import logging
from fnmatch import fnmatch
from pathlib import Path

logger = logging.getLogger(__name__)


class DbtModelSelector:
    """Selects dbt models based on name patterns and tags."""

    def __init__(
        self,
        select_patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
        verbose: bool = False,
    ) -> None:
        """
        Initialize dbt model selector.

        Args:
            select_patterns: List of selection patterns (e.g., ["my_model", "tag:nightly"])
            exclude_patterns: List of exclusion patterns (e.g., ["deprecated", "tag:test"])
            verbose: Enable verbose logging
        """
        self.select_patterns = select_patterns or []
        self.exclude_patterns = exclude_patterns or []
        self.verbose = verbose

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
        Check if dbt model name matches any of the patterns.

        Supports exact match and wildcard patterns (*, ?).

        Args:
            model_name: dbt model name (file name without extension)
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
            # Exact match
            if model_name == pattern or model_name.lower() == pattern.lower():
                return True

        return False

    def _has_tag(self, tags: list[str], tag: str) -> bool:
        """
        Check if model has the specified tag.

        Args:
            tags: List of tags for the model
            tag: Tag to check for

        Returns:
            True if model has the tag
        """
        if not tags:
            return False

        return tag in tags or tag.lower() in [t.lower() for t in tags]

    def _matches_tags(self, tags: list[str], tag_patterns: list[str]) -> bool:
        """
        Check if model matches any of the specified tag patterns.

        Args:
            tags: List of tags for the model
            tag_patterns: List of tags to check for

        Returns:
            True if model has any of the tags
        """
        if not tag_patterns:
            return False

        return any(self._has_tag(tags, tag_pattern) for tag_pattern in tag_patterns)

    def is_selected(
        self,
        model_name: str,
        model_tags: list[str] | None = None,
    ) -> bool:
        """
        Determine if a dbt model should be selected based on selection and exclusion criteria.

        Selection logic:
        1. If no select patterns, all models are selected (unless excluded)
        2. Model must match at least one select pattern (name or tag)
        3. Model must not match any exclude pattern (name or tag)

        Args:
            model_name: dbt model name (file name without extension)
            model_tags: List of tags for the model (optional)

        Returns:
            True if model should be included, False otherwise
        """
        tags = model_tags or []

        # If no select patterns, all models are selected by default
        if not self.select_patterns:
            # Only check exclusion
            if self.exclude_patterns:
                return not self._is_excluded(model_name, tags)
            return True

        # Check if model matches selection criteria
        matches_select = False

        # Check name patterns
        if self.select_names:
            matches_select = matches_select or self._matches_name(model_name, self.select_names)

        # Check tag patterns
        if self.select_tags:
            matches_select = matches_select or self._matches_tags(tags, self.select_tags)

        if not matches_select:
            return False

        # Check exclusion
        if self.exclude_patterns:
            return not self._is_excluded(model_name, tags)

        return True

    def _is_excluded(self, model_name: str, tags: list[str]) -> bool:
        """
        Check if model is excluded by any exclusion pattern.

        Args:
            model_name: dbt model name
            tags: List of tags for the model

        Returns:
            True if model is excluded
        """
        # Excluded when matching a name pattern or a tag pattern
        if self.exclude_names and self._matches_name(model_name, self.exclude_names):
            return True
        if self.exclude_tags and self._matches_tags(tags, self.exclude_tags):  # noqa: SIM103
            return True
        return False

    def filter_models(
        self,
        model_files: dict[str, Path],
        model_tags_map: dict[str, list[str]],
    ) -> dict[str, Path]:
        """
        Filter model files based on selection and exclusion criteria.

        Args:
            model_files: Dictionary mapping relative paths to SQL model files
            model_tags_map: Dictionary mapping model names to their tags

        Returns:
            Filtered dictionary of model files
        """
        if not self.select_patterns and not self.exclude_patterns:
            if self.verbose:
                logger.debug("No selection criteria, including all models")
            return model_files

        filtered = {}
        selected_count = 0
        excluded_count = 0

        for rel_path, sql_file in model_files.items():
            # Extract model name from file path (file name without extension)
            model_name = sql_file.stem
            tags = model_tags_map.get(model_name, [])

            if self.is_selected(model_name, tags):
                filtered[rel_path] = sql_file
                selected_count += 1
            else:
                excluded_count += 1
                if self.verbose:
                    reason = "excluded" if self._is_excluded(model_name, tags) else "not selected"
                    logger.debug(f"Model {model_name} {reason}")

        if self.verbose:
            logger.info(
                f"Filtered models: {selected_count} selected, {excluded_count} excluded "
                f"(from {len(model_files)} total)"
            )

        return filtered
