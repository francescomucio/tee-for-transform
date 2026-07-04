"""
Macro to UDF converter for dbt projects.

Converts simple dbt macros to t4t UDFs.
"""

import logging
import re
from pathlib import Path
from typing import Any

import sqlglot

from t4t.importer.common.jinja_utils import (
    has_adapter_specific_features,
    has_complex_jinja,
    has_dbt_specific_functions,
)
from t4t.importer.common.path_utils import ensure_directory_exists, extract_schema_from_path
from t4t.importer.dbt.constants import (
    DEFAULT_SCHEMA,
    FUNCTIONS_DIR,
    MACROS_DIR,
    PYTHON_EXTENSION,
    SQL_EXTENSION,
)

logger = logging.getLogger(__name__)


class MacroConverter:
    """Converts dbt macros to t4t UDFs."""

    def __init__(
        self,
        target_path: Path,
        target_dialect: str | None = None,
        default_schema: str = DEFAULT_SCHEMA,
        verbose: bool = False,
    ) -> None:
        """
        Initialize macro converter.

        Args:
            target_path: Path where t4t project will be created
            target_dialect: Target database dialect (e.g., "postgresql", "snowflake", "duckdb")
                          If None, defaults to PostgreSQL syntax
            default_schema: Default schema name for functions (default: DEFAULT_SCHEMA)
            verbose: Enable verbose logging
        """
        self.target_path = Path(target_path).resolve()
        # Normalize dialect name (SQLGlot uses "postgres" not "postgresql")
        self.target_dialect = self._normalize_dialect(target_dialect or "postgres")
        self.default_schema = default_schema
        self.verbose = verbose
        self.conversion_log: list[dict[str, Any]] = []

    def _normalize_dialect(self, dialect: str) -> str:
        """
        Normalize dialect name to SQLGlot format.

        Args:
            dialect: Dialect name (e.g., "postgresql", "postgres")

        Returns:
            Normalized dialect name for SQLGlot
        """
        # Map common dialect names to SQLGlot names
        dialect_map = {
            "postgresql": "postgres",
            "postgres": "postgres",
            "snowflake": "snowflake",
            "duckdb": "duckdb",
            "bigquery": "bigquery",
            "mysql": "mysql",
            "sqlite": "sqlite",
        }
        return dialect_map.get(dialect.lower(), dialect.lower())

    def convert_macros(self, all_macros: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        """
        Convert dbt macros to t4t UDFs.

        Args:
            all_macros: Dictionary mapping macro names to lists of macro definitions

        Returns:
            Dictionary with conversion statistics:
            - converted: Number of macros converted to UDFs
            - unconvertible: Number of macros that couldn't be converted
            - conversion_log: List of conversion results
        """
        converted_count = 0
        unconvertible_count = 0

        for macro_name, macro_defs in all_macros.items():
            # Skip adapter dispatch macros (they're not actual implementations)
            if any("adapter.dispatch" in m["body"] for m in macro_defs):
                self.conversion_log.append(
                    {
                        "macro": macro_name,
                        "status": "skipped",
                        "reason": "Adapter dispatch macro (not a concrete implementation)",
                    }
                )
                continue

            # Find the default implementation (non-adapter-specific)
            default_macro = None
            for macro_def in macro_defs:
                if not macro_def["adapter_specific"]:
                    default_macro = macro_def
                    break

            # If no default, use the first one
            if not default_macro:
                default_macro = macro_defs[0]

            # Check if macro can be converted
            if self._can_convert_macro(default_macro):
                try:
                    self._convert_macro_to_udf(default_macro, macro_defs)
                    converted_count += 1
                    self.conversion_log.append(
                        {
                            "macro": macro_name,
                            "status": "converted",
                            "udf_name": default_macro["base_name"],
                        }
                    )
                except Exception as e:
                    unconvertible_count += 1
                    logger.warning(f"Error converting macro {macro_name}: {e}")
                    self.conversion_log.append(
                        {
                            "macro": macro_name,
                            "status": "error",
                            "error": str(e),
                        }
                    )
            else:
                unconvertible_count += 1
                reason = self._get_unconvertible_reason(default_macro)
                self.conversion_log.append(
                    {
                        "macro": macro_name,
                        "status": "unconvertible",
                        "reason": reason,
                    }
                )

        return {
            "converted": converted_count,
            "unconvertible": unconvertible_count,
            "total": len(all_macros),
            "conversion_log": self.conversion_log,
        }

    def _can_convert_macro(self, macro_def: dict[str, Any]) -> bool:
        """
        Check if a macro can be converted to a UDF.

        Simple macros that can be converted:
        - Return SQL expressions (not complex logic)
        - Don't use adapter-specific features
        - Don't have complex Jinja (loops, conditionals beyond simple if)

        Args:
            macro_def: Macro definition dictionary

        Returns:
            True if macro can be converted
        """
        body = macro_def["body"]

        # Check for complex Jinja patterns
        if has_complex_jinja(body):
            return False

        # Check for adapter-specific features
        if has_adapter_specific_features(body):
            return False

        # Check for dbt-specific functions that can't be converted
        if has_dbt_specific_functions(body):
            return False

        # If it's mostly SQL with simple variable substitution, it's convertible
        return True

    def _get_unconvertible_reason(self, macro_def: dict[str, Any]) -> str:
        """
        Get reason why a macro cannot be converted.

        Args:
            macro_def: Macro definition dictionary

        Returns:
            Reason string
        """
        body = macro_def["body"]

        if has_complex_jinja(body):
            from t4t.importer.common.jinja_utils import get_complex_jinja_reason

            return get_complex_jinja_reason(body)
        if has_adapter_specific_features(body):
            return "Uses adapter-specific features"
        if has_dbt_specific_functions(body):
            return "Uses dbt-specific functions"
        return "Unknown reason"

    def _convert_macro_to_udf(
        self, default_macro: dict[str, Any], _all_versions: list[dict[str, Any]]
    ) -> None:
        """
        Convert a macro to a t4t UDF.

        Args:
            default_macro: Default macro definition
            _all_versions: All versions of the macro (including adapter-specific; reserved)
        """
        macro_name = default_macro["base_name"]
        parameters = default_macro["parameters"]
        body = default_macro["body"]

        # Clean up the macro body - remove Jinja variable references
        # Replace {{ param }} with just param (for SQL generation)
        sql_body = body
        for param in parameters:
            # Replace {{ param }} with param
            sql_body = re.sub(
                rf"\{{{{\s*{re.escape(param)}\s*}}\}}",
                param,
                sql_body,
                flags=re.IGNORECASE,
            )

        # Remove any remaining simple Jinja expressions
        # This is a simplified conversion - complex macros should be handled manually
        sql_body = re.sub(r"\{\{[^}]*\}\}", "", sql_body).strip()

        # Determine schema (use default_schema, or extract from macro file path)
        macro_file = Path(default_macro["file"])
        schema = extract_schema_from_path(macro_file, MACROS_DIR) or self.default_schema

        # Create function directory
        func_dir = self.target_path / FUNCTIONS_DIR / schema
        ensure_directory_exists(func_dir / "placeholder.txt")  # Ensure directory exists
        # Remove placeholder file if it was created
        placeholder = func_dir / "placeholder.txt"
        if placeholder.exists():
            placeholder.unlink()

        # Generate SQL function file
        sql_file = func_dir / f"{macro_name}{SQL_EXTENSION}"
        sql_content = self._generate_sql_function(macro_name, parameters, sql_body, schema)
        sql_file.write_text(sql_content, encoding="utf-8")

        # Generate Python metadata file
        py_file = func_dir / f"{macro_name}{PYTHON_EXTENSION}"
        py_content = self._generate_python_metadata(macro_name, parameters, schema, default_macro)
        py_file.write_text(py_content, encoding="utf-8")

        if self.verbose:
            logger.info(f"Converted macro {macro_name} to UDF at {sql_file}")

    def _generate_sql_function(
        self, function_name: str, parameters: list[str], body: str, schema: str
    ) -> str:
        """
        Generate SQL function definition for target dialect.

        Args:
            function_name: Name of the function
            parameters: List of parameter names
            body: Function body (SQL)
            schema: Schema name

        Returns:
            SQL function definition in target dialect
        """
        # Build parameter list (all parameters default to TEXT - type inference is complex)
        param_list = ", ".join(f"{p} TEXT" for p in parameters) if parameters else ""

        # Generate PostgreSQL-style function (as base template)
        # Note: Type inference is complex, so we default to TEXT
        # Users can manually adjust types after import
        base_sql = f"""-- Function converted from dbt macro: {function_name}
CREATE OR REPLACE FUNCTION {schema}.{function_name}(
    {param_list}
) RETURNS TEXT
LANGUAGE SQL
AS $$
    {body}
$$;
"""

        # Convert to target dialect using SQLGlot
        try:
            # Parse as PostgreSQL (source dialect for dbt macros)
            # SQLGlot uses "postgres" not "postgresql"
            parsed = sqlglot.parse_one(base_sql, read="postgres")

            # Convert to target dialect
            if self.target_dialect != "postgres":
                converted_sql = parsed.sql(dialect=self.target_dialect)
                if self.verbose:
                    logger.debug(
                        f"Converted function {function_name} from PostgreSQL to {self.target_dialect}"
                    )
                return converted_sql
            else:
                return base_sql
        except Exception as e:
            # If conversion fails, return PostgreSQL version with warning
            logger.warning(
                f"Failed to convert function {function_name} to {self.target_dialect}: {e}. "
                f"Using PostgreSQL syntax. Please review and adjust manually."
            )
            return base_sql

    def _generate_python_metadata(
        self, function_name: str, parameters: list[str], schema: str, macro_def: dict[str, Any]
    ) -> str:
        """
        Generate Python metadata file for the function.

        Args:
            function_name: Name of the function
            parameters: List of parameter names
            schema: Schema name

        Returns:
            Python metadata file content
        """
        param_defs = []
        for param in parameters:
            param_defs.append(f'        {{"name": "{param}", "type": "TEXT"}}')

        # Try to extract description from macro comments
        description = self._extract_description_from_macro(macro_def)

        metadata = f"""# Function metadata converted from dbt macro: {function_name}
from t4t.typing.metadata import FunctionMetadata

metadata: FunctionMetadata = {{
    "function_name": "{function_name}",
    "description": "{description}",
    "function_type": "scalar",
    "language": "sql",
    "parameters": [
{",\\n".join(param_defs)}
    ],
    "return_type": "TEXT",
    "schema": "{schema}",
}}
"""

        return metadata

    def _extract_description_from_macro(self, macro_def: dict[str, Any]) -> str:
        """
        Extract description from macro comments.

        Looks for comments like {# Description #} at the start of the macro.

        Args:
            macro_def: Macro definition dictionary

        Returns:
            Description string, or generic fallback
        """
        file_path = macro_def.get("file", "")

        # Try to read the original file to get comments
        try:
            if file_path:
                file_content = Path(file_path).read_text(encoding="utf-8")
                # Look for {# ... #} comments before the macro definition
                macro_name = macro_def.get("name", "")
                # Find the macro definition
                escaped_name = re.escape(macro_name)
                # Build pattern with proper escaping
                macro_pattern = r"\{\%\s*macro\s+" + escaped_name
                match = re.search(macro_pattern, file_content, re.IGNORECASE)
                if match:
                    # Look backwards for comments
                    before_macro = file_content[: match.start()]
                    # Find last comment block
                    comment_pattern = r"\{#\s*(.+?)\s*#\}"
                    comments = re.findall(comment_pattern, before_macro, re.DOTALL)
                    if comments:
                        # Use the last comment before the macro
                        description = comments[-1].strip()
                        # Clean up multi-line comments
                        description = re.sub(r"\s+", " ", description)
                        if description:
                            return description.replace('"', '\\"')
        except (AttributeError, FileNotFoundError, IndexError, KeyError, TypeError) as e:
            # Log but don't fail - fallback description will be used
            if self.verbose:
                logger.debug(f"Could not extract description from macro: {e}")
            pass

        # Fallback to generic description
        return "Function converted from dbt macro"
