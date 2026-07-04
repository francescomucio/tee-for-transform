"""
Function body extraction from SQL content.
"""

import re


class FunctionBodyExtractor:
    """Extracts function body from SQL content."""

    @staticmethod
    def extract(content: str) -> str:
        """
        Extract function body from SQL content.

        Args:
            content: SQL content

        Returns:
            Function body string (may be empty)
        """
        # Try with delimiters first ($$, quotes)
        as_match = re.search(
            r"AS\s+(?:\$\$|['\"`])(.*?)(?:\$\$|['\"`])", content, re.IGNORECASE | re.DOTALL
        )
        if as_match:
            return as_match.group(1).strip()

        # Try without delimiters
        as_match = re.search(r"AS\s+(.*?)(?:LANGUAGE|;|$)", content, re.IGNORECASE | re.DOTALL)
        if as_match:
            body = as_match.group(1).strip()
            # Remove delimiter markers if present
            if body.startswith("$$"):
                body = body[2:]
            if body.endswith("$$"):
                body = body[:-2]
            # For MACRO, remove parentheses if present
            if body.startswith("(") and body.endswith(")"):
                body = body[1:-1].strip()
            return body.strip()

        return ""
