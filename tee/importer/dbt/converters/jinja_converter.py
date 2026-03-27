"""
Jinja template converter for dbt models.

Converts dbt Jinja templates to t4t-compatible SQL or Python models.
"""

import logging
import re
from typing import Any

from tee.importer.common.jinja_utils import has_complex_jinja

logger = logging.getLogger(__name__)


class JinjaConverter:
    """Converts Jinja templates in dbt SQL to t4t format."""

    def __init__(
        self,
        dbt_project: dict[str, Any],
        model_name_map: dict[str, str] | None = None,
        source_map: dict[str, dict[str, str]] | None = None,
        verbose: bool = False,
        keep_jinja: bool = False,
        jinja_renderer: Any | None = None,
    ) -> None:
        """
        Initialize Jinja converter.

        Args:
            dbt_project: Parsed dbt project configuration
            model_name_map: Mapping of dbt model names to final table names
            source_map: Mapping of source names to schema.table format
            verbose: Enable verbose logging
            keep_jinja: Keep Jinja2 templates (only converts ref/source)
            jinja_renderer: Optional Jinja2 renderer for full macro support
        """
        self.dbt_project = dbt_project
        self.model_name_map = model_name_map or {}
        self.source_map = source_map or {}
        self.verbose = verbose
        self.keep_jinja = keep_jinja
        self.jinja_renderer = jinja_renderer

    def convert(self, sql_content: str, model_name: str | None = None) -> dict[str, Any]:
        """
        Convert Jinja templates in SQL content.

        Args:
            sql_content: Original SQL content with Jinja templates
            model_name: Name of the model (for context in error messages)

        Returns:
            Dictionary with:
            - 'sql': Converted SQL (or None if conversion failed)
            - 'is_python_model': True if should be converted to Python model
            - 'conversion_errors': List of error messages
            - 'conversion_warnings': List of warning messages
        """
        result = {
            "sql": None,
            "is_python_model": False,
            "conversion_errors": [],
            "conversion_warnings": [],
            "variables": [],  # Track variables used in the model
        }

        # Check if SQL contains Jinja
        if not self._has_jinja(sql_content):
            result["sql"] = sql_content
            return result

        # If we have a Jinja2 renderer, use it for full macro support
        if self.jinja_renderer:
            try:
                rendered_sql = self.jinja_renderer.render(sql_content, model_name)
                result["sql"] = rendered_sql
                if self.verbose:
                    logger.info(
                        f"Rendered model {model_name or 'unknown'} through Jinja2 with macros"
                    )
                return result
            except Exception as e:
                result["conversion_errors"].append(
                    f"Jinja2 rendering failed for model {model_name or 'unknown'}: {e}"
                )
                logger.warning(f"Jinja2 rendering failed for {model_name}: {e}")
                # Fall through to regular conversion

        # If keep_jinja is enabled, only convert ref() and source(), leave rest as Jinja
        if self.keep_jinja:
            converted_sql = sql_content

            # Convert ref() calls
            converted_sql = self._convert_refs(converted_sql, result, model_name)

            # Convert source() calls
            converted_sql = self._convert_sources(converted_sql, result, model_name)

            # Note: var() calls are left as Jinja - will be handled by t4t's Jinja2 support
            result["sql"] = converted_sql
            result["conversion_warnings"].append(
                f"Model {model_name or 'unknown'} contains Jinja2 templates that will be preserved. "
                "Note: Full Jinja2 support in t4t is coming soon (see issue #04-jinja2-support)."
            )
            if self.verbose:
                logger.info(f"Preserved Jinja2 templates in model {model_name or 'unknown'}")
            return result

        # Extract variables from if statements (do this before detecting complex Jinja)
        self._extract_variables_from_if_statements(sql_content, result)

        # Convert ref() and source() calls even for Python models (they need clean SQL)
        # This is a temporary SQL for conversion purposes
        temp_sql = sql_content
        temp_sql = self._convert_refs(temp_sql, result, model_name)
        temp_sql = self._convert_sources(temp_sql, result, model_name)

        # Store the converted SQL (with ref/source converted) for Python model generation
        result["sql_with_refs_converted"] = temp_sql

        # Detect complex Jinja patterns
        if self._has_complex_jinja(sql_content):
            result["is_python_model"] = True
            result["conversion_warnings"].append(
                f"Model {model_name or 'unknown'} contains complex Jinja (loops, conditionals, etc.). "
                "Will be converted to Python model."
            )
            return result

        # Attempt simple conversions
        try:
            converted_sql = sql_content

            # Convert ref() calls
            converted_sql = self._convert_refs(converted_sql, result, model_name)

            # Convert source() calls
            converted_sql = self._convert_sources(converted_sql, result, model_name)

            # Convert var() calls
            converted_sql = self._convert_vars(converted_sql, result, model_name)

            # Check if there are any remaining Jinja patterns
            if self._has_jinja(converted_sql):
                result["is_python_model"] = True
                result["conversion_warnings"].append(
                    f"Model {model_name or 'unknown'} contains unconvertible Jinja patterns. "
                    "Will be converted to Python model."
                )
                return result

            result["sql"] = converted_sql
            if self.verbose:
                logger.info(f"Successfully converted Jinja in model {model_name or 'unknown'}")

        except Exception as e:
            result["is_python_model"] = True
            result["conversion_errors"].append(
                f"Error converting Jinja in model {model_name or 'unknown'}: {e}"
            )
            logger.warning(f"Jinja conversion failed for {model_name}: {e}")

        return result

    def _has_jinja(self, content: str) -> bool:
        """Check if content contains Jinja templates."""
        return "{{" in content or "{%" in content

    def _has_complex_jinja(self, content: str) -> bool:
        """
        Detect complex Jinja patterns that require Python model conversion.

        Uses common utility function for consistency with macro converter.
        """
        return has_complex_jinja(content)

    def _convert_refs(self, sql: str, result: dict[str, Any], model_name: str | None) -> str:
        """
        Convert {{ ref('model_name') }} to table names.

        Args:
            sql: SQL content
            result: Result dictionary to update with warnings/errors
            model_name: Model name for context

        Returns:
            Converted SQL
        """
        # Pattern: {{ ref('model_name') }} or {{ ref("model_name") }}
        ref_pattern = r"\{\{\s*ref\s*\(\s*['\"]([^'\"]+)['\"]\s*\)\s*\}\}"

        def replace_ref(match: re.Match[str]) -> str:
            dbt_model_name = match.group(1)

            # Look up in model_name_map
            if dbt_model_name in self.model_name_map:
                table_name = self.model_name_map[dbt_model_name]
                if self.verbose:
                    logger.debug(f"Converted ref('{dbt_model_name}') to '{table_name}'")
                return table_name
            else:
                # Model not found - log warning and use model name as-is
                warning = (
                    f"Could not resolve ref('{dbt_model_name}') in model {model_name or 'unknown'}"
                )
                result["conversion_warnings"].append(warning)
                logger.warning(warning)
                # Use the model name as table name (might work if schema matches)
                return dbt_model_name

        return re.sub(ref_pattern, replace_ref, sql, flags=re.IGNORECASE)

    def _convert_sources(self, sql: str, result: dict[str, Any], model_name: str | None) -> str:
        """
        Convert {{ source('schema', 'table') }} to schema.table format.

        Args:
            sql: SQL content
            result: Result dictionary to update with warnings/errors
            model_name: Model name for context

        Returns:
            Converted SQL
        """
        # Pattern: {{ source('source_name', 'table_name') }}
        source_pattern = (
            r"\{\{\s*source\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)\s*\}\}"
        )

        def replace_source(match: re.Match[str]) -> str:
            source_name = match.group(1)
            table_name = match.group(2)

            # Look up in source_map
            if source_name in self.source_map and table_name in self.source_map[source_name]:
                schema_table = self.source_map[source_name][table_name]
                if self.verbose:
                    logger.debug(
                        f"Converted source('{source_name}', '{table_name}') to '{schema_table}'"
                    )
                return schema_table
            else:
                # Source not found - use default schema.table format
                # Most dbt sources use the source name as schema
                schema_table = f"{source_name}.{table_name}"
                warning = (
                    f"Could not resolve source('{source_name}', '{table_name}') in model {model_name or 'unknown'}. "
                    f"Using '{schema_table}' as fallback."
                )
                result["conversion_warnings"].append(warning)
                logger.warning(warning)
                return schema_table

        return re.sub(source_pattern, replace_source, sql, flags=re.IGNORECASE)

    def _convert_vars(self, sql: str, result: dict[str, Any], model_name: str | None) -> str:
        """
        Convert {{ var('var_name') }} or {{ var('var_name', 'default') }} to t4t variable syntax.

        Note: t4t uses --vars JSON format, so we'll convert to a placeholder
        that can be substituted later, or document the variable usage.

        Args:
            sql: SQL content
            result: Result dictionary to update with warnings/errors
            model_name: Model name for context

        Returns:
            Converted SQL (with variables as placeholders or removed)
        """
        # Pattern: {{ var('var_name') }} or {{ var('var_name', 'default') }}
        var_pattern = (
            r"\{\{\s*var\s*\(\s*['\"]([^'\"]+)['\"]\s*(?:,\s*['\"]([^'\"]+)['\"])?\s*\)\s*\}\}"
        )

        def replace_var(match: re.Match[str]) -> str:
            var_name = match.group(1)
            default_value = match.group(2) if match.group(2) else None

            # Track variable for Python model generation
            if var_name not in result.get("variables", []):
                if "variables" not in result:
                    result["variables"] = []
                result["variables"].append(var_name)

            # Convert to t4t variable syntax: @variable:default or @variable
            if default_value:
                # Variable with default: @variable:default
                if self.verbose:
                    logger.debug(
                        f"Converted var('{var_name}', '{default_value}') to '@{var_name}:{default_value}'"
                    )
                return f"@{var_name}:{default_value}"
            else:
                # Variable without default: @variable
                warning = (
                    f"Variable '{var_name}' used in model {model_name or 'unknown'} without default. "
                    "Will need to be provided via --vars flag."
                )
                result["conversion_warnings"].append(warning)
                if self.verbose:
                    logger.debug(f"Converted var('{var_name}') to '@{var_name}'")
                return f"@{var_name}"

        return re.sub(var_pattern, replace_var, sql, flags=re.IGNORECASE)

    def _extract_variables_from_if_statements(
        self, sql_content: str, result: dict[str, Any]
    ) -> None:
        """
        Extract variable names from {% if var(...) %} statements.

        Args:
            sql_content: Original SQL content
            result: Result dictionary to update with variables
        """
        # Pattern: {% if var('name') %} or {% if var('name', 'default') %}
        if_pattern = r"\{\%\s*if\s+.*?var\s*\(\s*['\"]([^'\"]+)['\"]"

        for match in re.finditer(if_pattern, sql_content, re.IGNORECASE | re.DOTALL):
            var_name = match.group(1)
            if "variables" not in result:
                result["variables"] = []
            if var_name not in result["variables"]:
                result["variables"].append(var_name)
