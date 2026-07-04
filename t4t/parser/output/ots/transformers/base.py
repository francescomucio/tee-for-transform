"""Base transformer class for OTS transformation strategies."""

from abc import ABC, abstractmethod
from typing import Any

from ..taggers.tag_manager import TagManager


class BaseTransformer(ABC):
    """Base class for transformation strategies."""

    def __init__(self, project_config: dict[str, Any]):
        """
        Initialize the base transformer.

        Args:
            project_config: Project configuration dictionary
        """
        self.project_config = project_config
        self.tag_manager = TagManager(project_config)

    @abstractmethod
    def transform(self, entity_id: str, entity_data: dict[str, Any], schema: str) -> dict[str, Any]:
        """
        Transform an entity to OTS format.

        Args:
            entity_id: Entity identifier (e.g., "my_schema.table")
            entity_data: Parsed entity data
            schema: Schema name

        Returns:
            Transformed entity as OTS structure
        """
        pass
