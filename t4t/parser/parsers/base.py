"""
Abstract base parser class for all parsers.
"""

from abc import ABC, abstractmethod

from t4t.parser.shared.types import FilePath, ParsedModel


class BaseParser(ABC):
    """Abstract base class for all parsers."""

    def __init__(self):
        """Initialize the parser."""
        self._cache: dict[str, ParsedModel] = {}

    def clear_cache(self) -> None:
        """Clear the parser cache."""
        self._cache.clear()

    @abstractmethod
    def parse(self, content: str, file_path: FilePath = None) -> ParsedModel:
        """
        Parse content and return parsed model data.

        Args:
            content: The content to parse
            file_path: Optional file path for context

        Returns:
            Parsed model data

        Raises:
            ParserError: If parsing fails
        """
        pass

    def _get_cache_key(self, content: str, file_path: FilePath = None) -> str:
        """Generate a cache key for the given content and file path."""
        if file_path:
            return f"{file_path}:{hash(content)}"
        return str(hash(content))

    def _get_from_cache(self, cache_key: str) -> ParsedModel:
        """Get parsed data from cache."""
        return self._cache.get(cache_key)

    def _set_cache(self, cache_key: str, data: ParsedModel) -> None:
        """Store parsed data in cache."""
        self._cache[cache_key] = data
