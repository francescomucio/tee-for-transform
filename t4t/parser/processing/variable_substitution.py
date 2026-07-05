"""
SQL Variable Substitution

Handles variable substitution in SQL content using @variable_name and {{ variable_name }} syntax.
Supports nested object access, default values, and proper error handling.
"""

import re
from typing import Any

from t4t.parser.shared.constants import SQL_VARIABLE_PATTERNS
from t4t.parser.shared.exceptions import VariableSubstitutionError
from t4t.parser.shared.types import Variables


def _format_sql_value(value: Any) -> str:
    """
    Format a Python value for use in SQL.

    Args:
        value: The value to format

    Returns:
        SQL-formatted string representation of the value
    """
    if value is None:
        return "NULL"
    elif isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    elif isinstance(value, (int, float)):
        return str(value)
    elif isinstance(value, str):
        # Escape single quotes by doubling them
        escaped_value = value.replace("'", "''")
        return f"'{escaped_value}'"
    else:
        # For other types, convert to string and quote
        escaped_value = str(value).replace("'", "''")
        return f"'{escaped_value}'"


def get_nested_value(data: dict[str, Any], key_path: str) -> Any:
    """
    Get a nested value from a dictionary using dot notation.

    Args:
        data: Dictionary to search in
        key_path: Dot-separated path (e.g., 'config.database.host')

    Returns:
        The value at the specified path

    Raises:
        KeyError: If the path doesn't exist
    """
    keys = key_path.split(".")
    current = data

    for i, key in enumerate(keys):
        if not isinstance(current, dict) or key not in current:
            # Build the path up to the missing key
            path_so_far = ".".join(keys[: i + 1])
            raise KeyError(f"Key '{path_so_far}' not found")
        current = current[key]

    return current


def substitute_sql_variables(sql_content: str, variables: Variables) -> str:
    """
    Substitute variables in SQL content using @variable_name and {{ variable_name }} syntax.

    Supports:
    - @variable_name syntax
    - @variable_name:default syntax
    - {{ variable_name }} syntax (Jinja-style)
    - {{ variable_name | default('value') }} syntax with defaults
    - Nested object access with dot notation (e.g., config.database.host)

    Args:
        sql_content: SQL content with variable placeholders
        variables: Dictionary of variables for substitution

    Returns:
        SQL content with variables substituted

    Raises:
        VariableSubstitutionError: If variable substitution fails
    """
    try:
        result = sql_content

        # If no variables provided, return original SQL unchanged
        if not variables:
            return result

        # Handle @variable_name:default syntax first
        at_with_default_pattern = r"@(\w+(?:\.\w+)*):([^@\s]+)"
        for match in re.finditer(at_with_default_pattern, result):
            var_name = match.group(1)
            default_value = match.group(2).strip()

            try:
                value = get_nested_value(variables, var_name)
                sql_value = _format_sql_value(value)
            except KeyError:
                # Use default value
                sql_value = _format_sql_value(default_value)

            result = result.replace(match.group(0), sql_value)

        # Handle @variable_name syntax (without defaults)
        at_pattern = r"@(\w+(?:\.\w+)*)(?![:\w])"  # Match @variable but not @variable:default
        for match in re.finditer(at_pattern, result):
            var_name = match.group(1)
            try:
                value = get_nested_value(variables, var_name)
                sql_value = _format_sql_value(value)
                result = result.replace(f"@{var_name}", sql_value)
            except KeyError:
                # If variable is missing and no default, return original SQL (don't raise error)
                return sql_content

        # Handle {{ variable_name:default }} syntax first
        jinja_with_default_pattern = r"\{\{\s*(\w+(?:\.\w+)*)\s*:\s*([^}]+)\s*\}\}"
        for match in re.finditer(jinja_with_default_pattern, result):
            var_name = match.group(1).strip()
            default_value = match.group(2).strip()

            try:
                value = get_nested_value(variables, var_name)
                sql_value = _format_sql_value(value)
            except KeyError:
                # Use default value
                sql_value = _format_sql_value(default_value)

            result = result.replace(match.group(0), sql_value)

        # Handle {{ variable_name }} syntax (without defaults)
        jinja_pattern = SQL_VARIABLE_PATTERNS["jinja_variable"]
        for match in re.finditer(jinja_pattern, result):
            var_name = match.group(1).strip()
            try:
                value = get_nested_value(variables, var_name)
                sql_value = _format_sql_value(value)
                result = result.replace(match.group(0), sql_value)
            except KeyError:
                # If variable is missing and no default, return original SQL (don't raise error)
                return sql_content

        # Handle {{ variable_name | default('value') }} syntax
        jinja_default_pattern = SQL_VARIABLE_PATTERNS["jinja_with_default"]
        for match in re.finditer(jinja_default_pattern, result):
            var_name = match.group(1).strip()
            default_value = match.group(2).strip().strip("'\"")  # Remove quotes

            try:
                value = get_nested_value(variables, var_name)
                sql_value = _format_sql_value(value)
            except KeyError:
                # Use default value
                sql_value = _format_sql_value(default_value)

            result = result.replace(match.group(0), sql_value)

        return result

    except Exception as e:
        if isinstance(e, VariableSubstitutionError):
            raise
        raise VariableSubstitutionError(f"Variable substitution failed: {str(e)}") from e


def validate_sql_variables(sql_content: str, variables: Variables) -> dict[str, Any]:
    """
    Validate that all variables referenced in SQL content are available.

    Args:
        sql_content: SQL content to validate
        variables: Dictionary of available variables

    Returns:
        Dict with validation result

    Raises:
        VariableSubstitutionError: If validation fails
    """
    try:
        missing_vars = []
        referenced_vars = []

        # Check @variable_name syntax (without defaults)
        at_pattern = SQL_VARIABLE_PATTERNS["at_variable"]
        for match in re.finditer(at_pattern, sql_content):
            var_name = match.group(1)
            referenced_vars.append(var_name)
            # Skip if this is part of a @variable:default pattern
            if not re.search(rf"@{re.escape(var_name)}:", sql_content):
                try:
                    get_nested_value(variables, var_name)
                except KeyError:
                    missing_vars.append(f"@{var_name}")

        # Check {{ variable_name }} syntax
        jinja_pattern = SQL_VARIABLE_PATTERNS["jinja_variable"]
        for match in re.finditer(jinja_pattern, sql_content):
            var_name = match.group(1).strip()
            referenced_vars.append(var_name)
            try:
                get_nested_value(variables, var_name)
            except KeyError:
                missing_vars.append(f"{{{{ {var_name} }}}}")

        # Note: @variable:default and {{ variable_name | default('value') }} syntax
        # don't need validation as they have default values

        # Find unused variables
        referenced_vars_set = set(referenced_vars)
        unused_vars = [var for var in variables if var not in referenced_vars_set]

        if missing_vars:
            raise VariableSubstitutionError(
                f"Missing variables: {', '.join(missing_vars)}. "
                f"Available variables: {list(variables.keys())}"
            )

        return {
            "valid": True,
            "missing_vars": [],
            "referenced_vars": list(referenced_vars_set),
            "unused_vars": unused_vars,
        }

    except Exception as e:
        if isinstance(e, VariableSubstitutionError):
            raise
        raise VariableSubstitutionError(f"Variable validation failed: {str(e)}") from e
