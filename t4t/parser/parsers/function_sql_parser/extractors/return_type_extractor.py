"""
Return type extraction from SQL content.
"""

import re


class ReturnTypeExtractor:
    """Extracts function return type from SQL content."""

    @staticmethod
    def extract(content: str) -> str | None:
        """
        Extract return type from SQL content.

        Args:
            content: SQL content

        Returns:
            Return type string or None if not found
        """
        # Match RETURNS followed by type, stopping before AS or LANGUAGE
        returns_match = re.search(
            r"RETURNS\s+(\w+(?:\s+\w+)?)\s*(?=AS|LANGUAGE|;|$)", content, re.IGNORECASE
        )
        if returns_match:
            return returns_match.group(1).strip().upper()
        return None
