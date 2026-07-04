"""
Dependency extraction from function body SQL.
"""

import re

from t4t.parser.shared.constants import SQL_BUILT_IN_FUNCTIONS


class DependencyExtractor:
    """Extracts dependencies (tables and functions) from function body."""

    @staticmethod
    def extract(function_body: str) -> dict[str, list[str]]:
        """
        Extract dependencies from function body (table references and function calls).

        Args:
            function_body: Function body SQL

        Returns:
            Dict with 'tables' and 'functions' keys
        """
        dependencies = {"tables": [], "functions": []}

        if not function_body:
            return dependencies

        # Extract table references (FROM, JOIN clauses)
        # This is a simplified extraction - full parsing would use SQLglot
        table_pattern = r"(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?)"
        table_matches = re.findall(table_pattern, function_body, re.IGNORECASE)
        dependencies["tables"] = list(set(table_matches))

        # Extract function calls (simplified - look for identifier followed by parenthesis)
        # Filter out common built-in functions
        # Pattern: identifier( or schema.identifier( - function call
        # Support both unqualified and qualified function names
        func_pattern = r"([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?)\s*\("
        func_matches = re.findall(func_pattern, function_body, re.IGNORECASE)
        functions = [
            f.strip() for f in func_matches if f.strip().lower() not in SQL_BUILT_IN_FUNCTIONS
        ]
        dependencies["functions"] = list(set(functions))

        return dependencies
