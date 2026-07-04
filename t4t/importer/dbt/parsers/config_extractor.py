"""
Config block extractor for dbt model files.

Extracts {{ config(...) }} blocks from SQL model files.
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class ConfigExtractor:
    """Extracts config blocks from dbt model SQL files."""

    def __init__(self, verbose: bool = False) -> None:
        """
        Initialize config extractor.

        Args:
            verbose: Enable verbose logging
        """
        self.verbose = verbose

    def extract_config(self, sql_content: str) -> dict[str, Any]:
        """
        Extract config block from SQL content.

        Handles patterns like:
        - {{ config(schema='custom') }}
        - {{ config(materialized='table', schema='staging') }}
        - {{ config({"schema": "custom", "tags": ["tag1"]}) }}

        Args:
            sql_content: SQL content with potential config blocks

        Returns:
            Dictionary with extracted config values
        """
        config: dict[str, Any] = {}

        # Pattern 1: {{ config(key='value', key2='value2') }}
        # Matches: config(schema='custom'), config(materialized='table', schema='staging')
        pattern1 = r"\{\{\s*config\s*\(([^)]+)\)\s*\}\}"
        matches1 = re.finditer(pattern1, sql_content, re.IGNORECASE)

        for match in matches1:
            config_str = match.group(1)
            parsed = self._parse_config_arguments(config_str)
            config.update(parsed)

        # Pattern 2: {{ config({"key": "value"}) }}
        # Matches: config({"schema": "custom"})
        pattern2 = r"\{\{\s*config\s*\(\s*(\{[^}]+\})\s*\)\s*\}\}"
        matches2 = re.finditer(pattern2, sql_content, re.IGNORECASE)

        for match in matches2:
            dict_str = match.group(1)
            parsed = self._parse_config_dict(dict_str)
            config.update(parsed)

        if config and self.verbose:
            logger.debug(f"Extracted config from model: {config}")

        return config

    def _parse_config_arguments(self, args_str: str) -> dict[str, Any]:
        """
        Parse config arguments string like: schema='custom', materialized='table'.

        Args:
            args_str: Arguments string

        Returns:
            Dictionary with parsed config values
        """
        # Pattern to match key='value' or key="value" or key=value
        # Handles: schema='custom', tags=['tag1', 'tag2'], enabled=true
        pattern = r"(\w+)\s*=\s*((?:'[^']*'|\"[^\"]*\"|\[[^\]]*\]|\w+))"
        return self._parse_key_value_pairs(pattern, args_str)

    def _parse_config_dict(self, dict_str: str) -> dict[str, Any]:
        """
        Parse config dictionary string like: {"schema": "custom", "tags": ["tag1"]}.

        Args:
            dict_str: Dictionary string

        Returns:
            Dictionary with parsed config values
        """
        # Pattern to match "key": value or 'key': value
        # Handles: "schema": "custom", "tags": ["tag1", "tag2"]
        pattern = r"['\"]?(\w+)['\"]?\s*:\s*((?:'[^']*'|\"[^\"]*\"|\[[^\]]*\]|\w+))"
        return self._parse_key_value_pairs(pattern, dict_str)

    def _parse_key_value_pairs(self, pattern: str, content: str) -> dict[str, Any]:
        """
        Parse key-value pairs from content using a regex pattern.

        Args:
            pattern: Regex pattern with two groups: (key, value)
            content: String content to parse

        Returns:
            Dictionary with parsed key-value pairs
        """
        config: dict[str, Any] = {}
        for match in re.finditer(pattern, content):
            key = match.group(1)
            value_str = match.group(2).strip()
            config[key] = self._parse_value(value_str)
        return config

    def _parse_value(self, value_str: str) -> Any:
        """
        Parse a config value string based on its type.

        Handles:
        - Quoted strings ('value' or "value")
        - Lists ([...])
        - Booleans (true/false)
        - Numbers (int/float)
        - Unquoted strings

        Args:
            value_str: Value string to parse

        Returns:
            Parsed value (str, list, bool, int, float)
        """
        # Parse quoted strings
        if value_str.startswith("'") and value_str.endswith("'"):
            return value_str[1:-1]  # Remove quotes
        if value_str.startswith('"') and value_str.endswith('"'):
            return value_str[1:-1]  # Remove quotes

        # Parse lists
        if value_str.startswith("[") and value_str.endswith("]"):
            return self._parse_list(value_str)

        # Parse booleans
        if value_str.lower() in ("true", "false"):
            return value_str.lower() == "true"

        # Parse numbers
        if value_str.replace(".", "").replace("-", "").isdigit():
            try:
                return float(value_str) if "." in value_str else int(value_str)
            except ValueError:
                return value_str

        # Unquoted string (like a variable name)
        return value_str

    def _parse_list(self, list_str: str) -> list[str]:
        """
        Parse list string like: ['tag1', 'tag2'] or ["tag1", "tag2"].

        Args:
            list_str: List string

        Returns:
            List of parsed values
        """
        items: list[str] = []

        # Remove brackets
        content = list_str[1:-1].strip()
        if not content:
            return items

        # Pattern to match quoted strings in list
        pattern = r"['\"]([^'\"]+)['\"]"

        for match in re.finditer(pattern, content):
            items.append(match.group(1))

        return items
