"""Unified tag management for models and functions."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class TagManager:
    """Manages tag merging and extraction for models and functions."""

    def __init__(self, project_config: dict[str, Any]):
        """
        Initialize the tag manager.

        Args:
            project_config: Project configuration dictionary
        """
        self.project_config = project_config
        self._module_tags = self._extract_module_tags()

    def _extract_module_tags(self) -> list[str]:
        """
        Extract module-level tags from project configuration.

        Returns:
            List of module tags
        """
        module_tags = []
        if "module" in self.project_config:
            module_config = self.project_config.get("module", {})
            if isinstance(module_config, dict):
                module_tags = module_config.get("tags", [])
        elif "tags" in self.project_config:
            root_tags = self.project_config.get("tags", [])
            if isinstance(root_tags, list):
                module_tags = root_tags

        # Ensure module_tags is a list
        if not isinstance(module_tags, list):
            module_tags = []

        return module_tags

    def merge_tags(self, entity_tags: list[str]) -> list[str]:
        """
        Merge module tags with entity-specific tags.

        Args:
            entity_tags: Entity-specific tags (from model or function metadata)

        Returns:
            Merged and deduplicated list of tags
        """
        # Ensure entity_tags is a list
        if not isinstance(entity_tags, list):
            entity_tags = []

        # Merge and deduplicate while preserving order
        all_tags = self._module_tags + entity_tags
        seen = set()
        merged_tags = []
        for tag in all_tags:
            tag_str = str(tag).lower() if tag else ""
            if tag_str and tag_str not in seen:
                seen.add(tag_str)
                merged_tags.append(tag)

        return merged_tags

    def extract_object_tags(self, metadata: dict[str, Any]) -> dict[str, str]:
        """
        Extract and validate object_tags (database-style key-value pairs) from metadata.

        Args:
            metadata: Entity metadata dictionary

        Returns:
            Dictionary of validated object tags (key-value pairs)
        """
        # Extract object_tags from metadata
        object_tags = metadata.get("object_tags", {})
        if not isinstance(object_tags, dict):
            return {}

        # Validate that all values are strings (or convert them)
        validated_tags = {}
        for key, value in object_tags.items():
            if key and isinstance(key, str):
                # Convert value to string if it's not already
                if value is not None:
                    validated_tags[key] = str(value)

        return validated_tags
