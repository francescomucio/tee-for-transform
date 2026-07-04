"""
Function name extraction from SQLglot AST or regex matches.
"""

from sqlglot import exp


class FunctionNameExtractor:
    """Extracts function name and schema from various sources."""

    @staticmethod
    def extract_from_udf(udf: exp.UserDefinedFunction) -> tuple[str, str | None] | None:
        """
        Extract function name and schema from SQLglot UserDefinedFunction.

        Args:
            udf: SQLglot UserDefinedFunction expression

        Returns:
            Tuple of (function_name, schema) or None if extraction fails
        """
        function_name_full = ""
        if hasattr(udf, "this") and udf.this:
            if isinstance(udf.this, exp.Table) or isinstance(udf.this, exp.Identifier):
                function_name_full = udf.this.name if hasattr(udf.this, "name") else str(udf.this)
            else:
                function_name_full = str(udf.this)

        if not function_name_full:
            return None

        # Extract schema and function name
        if "." in function_name_full:
            parts = function_name_full.split(".")
            schema = parts[0]
            function_name = parts[1]
        else:
            schema = None
            function_name = function_name_full

        return function_name, schema

    @staticmethod
    def extract_from_string(function_name_full: str) -> tuple[str, str | None]:
        """
        Extract function name and schema from string.

        Args:
            function_name_full: Full function name (may include schema)

        Returns:
            Tuple of (function_name, schema)
        """
        if "." in function_name_full:
            parts = function_name_full.split(".")
            schema = parts[0]
            function_name = parts[1]
        else:
            schema = None
            function_name = function_name_full

        return function_name, schema
