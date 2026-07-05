"""
Python model generator for dbt models with complex Jinja.

Converts dbt models with complex Jinja patterns to t4t Python models.
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class PythonModelGenerator:
    """Generates Python model code from dbt SQL with Jinja templates."""

    def __init__(self, verbose: bool = False) -> None:
        """
        Initialize Python model generator.

        Args:
            verbose: Enable verbose logging
        """
        self.verbose = verbose

    def generate(
        self,
        sql_content: str,
        model_name: str,
        table_name: str,
        metadata: dict[str, Any] | None = None,
        variables: list[str] | None = None,
        conversion_warnings: list[str] | None = None,
    ) -> str:
        """
        Generate Python model code from dbt SQL with Jinja.

        Args:
            sql_content: Original SQL content with Jinja templates
            model_name: Name of the dbt model
            table_name: Final table name (schema.table)
            metadata: t4t metadata dictionary
            variables: List of variable names used in the model
            conversion_warnings: List of conversion warnings

        Returns:
            Python code as string
        """
        # Extract variables from Jinja if not provided
        if variables is None:
            variables = self._extract_variables(sql_content)

        # Generate Python code
        python_code = self._generate_python_code(
            sql_content, model_name, table_name, metadata, variables, conversion_warnings
        )

        # Ensure newline at end
        if not python_code.endswith("\n"):
            python_code += "\n"

        return python_code

    def _extract_variables(self, sql_content: str) -> list[str]:
        """Extract variable names from Jinja var() calls."""
        variables = set()

        # Pattern: {{ var('var_name') }} or {{ var('var_name', 'default') }}
        var_pattern = r"\{\{\s*var\s*\(\s*['\"]([^'\"]+)['\"]"
        for match in re.finditer(var_pattern, sql_content, re.IGNORECASE):
            var_name = match.group(1)
            variables.add(var_name)

        return sorted(variables)

    def _generate_python_code(
        self,
        sql_content: str,
        model_name: str,
        table_name: str,
        metadata: dict[str, Any] | None,
        variables: list[str],
        conversion_warnings: list[str] | None,
    ) -> str:
        """Generate Python model code."""
        lines = []

        # Header comment
        lines.append('"""')
        lines.append(f"Model converted from dbt: {model_name}")
        lines.append(f"Table: {table_name}")
        if conversion_warnings:
            lines.append("")
            lines.append("Conversion warnings:")
            for warning in conversion_warnings:
                lines.append(f"  - {warning}")
        lines.append('"""')

        # Imports
        lines.append("from t4t.parser.processing.model import model")
        if metadata:
            lines.append("from t4t.typing.metadata import ModelMetadata")
        lines.append("")

        # Metadata dict (if provided)
        if metadata:
            lines.append("# Model metadata")
            metadata_str = self._format_metadata_dict(metadata)
            lines.append(f"metadata: ModelMetadata = {metadata_str}")
            lines.append("")
        else:
            # Create empty metadata dict
            lines.append("metadata: ModelMetadata = {}")
            lines.append("")

        # Decorator
        decorator_args = [f'table_name="{table_name}"']
        if metadata and "description" in metadata:
            desc = metadata["description"].replace('"', '\\"')
            decorator_args.append(f'description="{desc}"')
        if variables:
            vars_str = "[" + ", ".join(f'"{v}"' for v in variables) + "]"
            decorator_args.append(f"variables={vars_str}")
        if metadata:
            decorator_args.append("**metadata")

        decorator_line = "@model(" + ", ".join(decorator_args) + ")"
        lines.append(decorator_line)

        # Function definition
        function_name = self._sanitize_function_name(model_name)
        lines.append(f"def {function_name}():")
        lines.append('    """')
        lines.append(f"    Generated model function for {table_name}")
        if conversion_warnings:
            lines.append("    ")
            lines.append(
                "    TODO: Review this conversion - complex Jinja was converted to Python."
            )
        lines.append('    """')

        # Function body - convert Jinja to Python
        function_body = self._convert_jinja_to_python(sql_content, variables)
        # Indent function body
        for line in function_body:
            if line.strip():
                lines.append("    " + line)
            else:
                lines.append("")

        return "\n".join(lines)

    def _format_metadata_dict(self, metadata: dict[str, Any]) -> str:
        """Format metadata dictionary as Python code."""
        # Simple formatting - could be improved
        import json

        # Use json for basic formatting, then adjust for Python
        json_str = json.dumps(metadata, indent=4)
        # Convert JSON null to Python None
        json_str = json_str.replace("null", "None")
        return json_str

    def _sanitize_function_name(self, name: str) -> str:
        """Convert model name to valid Python function name."""
        # Replace dots and dashes with underscores
        name = name.replace(".", "_").replace("-", "_")
        # Remove invalid characters
        name = re.sub(r"[^a-zA-Z0-9_]", "", name)
        # Ensure it starts with a letter or underscore
        if name and not name[0].isalpha() and name[0] != "_":
            name = "_" + name
        # If empty, use default
        if not name:
            name = "model"
        return name

    def _convert_jinja_to_python(self, sql_content: str, variables: list[str]) -> list[str]:
        """
        Convert Jinja templates to Python code.

        This is a simplified converter - it handles common patterns:
        - {% if %} / {% else %} / {% endif %}
        - {% for %} / {% endfor %}
        - {{ var() }} - variables
        - {{ ref() }} and {{ source() }} - should already be converted

        Returns:
            List of Python code lines
        """
        # Check if we can do a simple conversion or need fallback
        has_loops = "{% for" in sql_content.lower()
        has_complex_conditionals = (
            "{% else %}" in sql_content.lower() or "{% elif" in sql_content.lower()
        )
        has_simple_if = "{% if" in sql_content.lower() and not has_complex_conditionals

        # Try to convert simple if statements
        if has_simple_if and not has_loops:
            return self._convert_simple_if_statements(sql_content, variables)

        if has_loops or has_complex_conditionals:
            return self._generate_fallback_template(sql_content, variables)

        # No Jinja - should not happen (this function only called for Python models)
        return self._generate_fallback_template(sql_content, variables)

    def _convert_simple_if_statements(self, sql_content: str, variables: list[str]) -> list[str]:
        """
        Convert simple {% if %} statements to Python code.

        Handles patterns like:
        - {% if var('name') %}...{% endif %}
        - {% if var('name', false) %}...{% endif %}

        Variables are injected into the module namespace by t4t, so they're
        available as regular Python variables.

        Returns:
            List of Python code lines
        """
        lines = []
        lines.append("# Converted from dbt Jinja with simple if statements")
        lines.append("")

        # Extract if statements - need to handle multiline properly
        # Pattern: {% if ... %} ... {% endif %}
        # Match condition (anything until %}) and content (anything until {% endif %})
        if_pattern = r"\{\%\s*if\s+(.+?)\s*\%\}(.*?)\{\%\s*endif\s*\%\}"
        matches = list(re.finditer(if_pattern, sql_content, re.DOTALL | re.IGNORECASE))

        if not matches:
            # Fallback to template
            return self._generate_fallback_template(sql_content, variables)

        # Build SQL string with Python conditionals
        lines.append("# Build SQL string with conditional logic")
        lines.append("sql_parts = []")
        lines.append("")

        # Split SQL by if statements and convert
        last_end = 0

        for _i, match in enumerate(matches):
            # Add SQL before this if statement
            before_sql = sql_content[last_end : match.start()].strip()
            if before_sql:
                # Remove any remaining Jinja expressions (ref, source should already be converted)
                # But keep t4t variable syntax (@variable)
                before_sql = re.sub(r"\{\{[^@].*?\}\}", "", before_sql)
                if before_sql.strip():
                    # Escape quotes properly for triple-quoted string
                    escaped = before_sql.replace('"""', '\\"\\"\\"')
                    lines.append(f'sql_parts.append("""{escaped}""")')

            # Extract condition and content
            condition = match.group(1).strip()
            if_content = match.group(2).strip()

            # Parse condition - look for var() calls
            # Pattern: var('name') or var('name', 'default') or var('name', false)
            # Handle both quoted and unquoted default values
            var_match = re.search(
                r"var\s*\(\s*['\"]([^'\"]+)['\"]\s*(?:,\s*(['\"]?)([^'\"\),]+)\2)?\s*\)",
                condition,
                re.IGNORECASE,
            )
            if var_match:
                var_name = var_match.group(1)
                # Variables are injected into module namespace by t4t, so use directly
                lines.append(f"# Conditional: {condition}")
                lines.append(f"if {var_name}:")

                # Remove Jinja from if_content but keep t4t variables
                # First remove ref/source calls (should already be converted)
                clean_content = re.sub(r"\{\{[^@].*?\}\}", "", if_content).strip()
                if clean_content:
                    # Escape quotes properly
                    escaped = clean_content.replace('"""', '\\"\\"\\"')
                    lines.append(f'    sql_parts.append("""{escaped}""")')
                lines.append("")

            last_end = match.end()

        # Add remaining SQL after last if
        after_sql = sql_content[last_end:].strip()
        if after_sql:
            after_sql = re.sub(r"\{\{[^@].*?\}\}", "", after_sql)
            if after_sql.strip():
                escaped = after_sql.replace('"""', '\\"\\"\\"')
                lines.append(f'sql_parts.append("""{escaped}""")')

        lines.append("")
        lines.append("# Combine SQL parts")
        lines.append("sql = '\\n'.join(sql_parts)")
        lines.append("")
        lines.append("return sql")

        return lines

    def _generate_fallback_template(self, sql_content: str, variables: list[str]) -> list[str]:
        """Generate fallback template when conversion is not possible."""
        lines = []
        lines.append("# TODO: This model contains complex Jinja that needs manual conversion")
        lines.append("# Original SQL with Jinja:")
        lines.append("# " + "=" * 70)

        # Add original SQL as comment
        for sql_line in sql_content.split("\n"):
            lines.append(f"# {sql_line}")

        lines.append("# " + "=" * 70)
        lines.append("")

        # Generate fallback Python code
        lines.append("# Fallback: Return original SQL (needs manual conversion)")
        lines.append("# Variables are available in the function namespace")
        if variables:
            lines.append(f"# Available variables: {', '.join(variables)}")
        lines.append("")

        lines.append("# Build SQL string")
        lines.append("sql_parts = []")
        lines.append("")

        lines.append("# Original SQL preserved - convert Jinja manually")
        lines.append("original_sql = '''")
        # Escape triple quotes in SQL
        escaped_sql = sql_content.replace("'''", "''' + \"'''\" + '''")
        lines.append(escaped_sql)
        lines.append("'''")
        lines.append("")
        lines.append("# TODO: Convert Jinja templates to Python logic")
        lines.append("# Example:")
        if variables:
            for var in variables:
                lines.append(f"#   Replace {{ var('{var}') }} with: {var}")
        lines.append("")
        lines.append("# Return SQL string (validation happens in the parser)")
        lines.append("return original_sql")

        return lines
