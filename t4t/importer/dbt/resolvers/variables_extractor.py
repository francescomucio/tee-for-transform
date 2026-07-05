"""
Variables extractor for dbt projects.

Extracts and documents all dbt variables used in models.
"""

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class VariablesExtractor:
    """Extracts and documents dbt variables."""

    def __init__(self, verbose: bool = False) -> None:
        """
        Initialize variables extractor.

        Args:
            verbose: Enable verbose logging
        """
        self.verbose = verbose

    def extract_variables(
        self,
        model_files: dict[str, Path],
        dbt_project: dict[str, Any],
        _conversion_log: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Extract all variables from models and dbt_project.yml.

        Args:
            model_files: Dictionary mapping relative paths to SQL model files
            dbt_project: Parsed dbt project configuration
            _conversion_log: Conversion log from model converter (reserved)

        Returns:
            Dictionary with variable information:
            - variables: Dictionary mapping variable names to variable info
            - usage: Dictionary mapping variable names to list of models using them
        """
        variables: dict[str, Any] = {}
        usage: dict[str, list[str]] = {}

        # Extract variables from dbt_project.yml
        project_vars = dbt_project.get("vars", {})
        for var_name, var_value in project_vars.items():
            variables[var_name] = {
                "name": var_name,
                "default_value": var_value,
                "defined_in": "dbt_project.yml",
                "used_in": [],
            }

        # Extract variables from model files
        var_pattern = (
            r"\{\{\s*var\s*\(\s*['\"]([^'\"]+)['\"]\s*(?:,\s*['\"]([^'\"]+)['\"])?\s*\)\s*\}\}"
        )
        if_pattern = r"\{\%\s*if\s+.*?var\s*\(\s*['\"]([^'\"]+)['\"]"

        for rel_path, sql_file in model_files.items():
            try:
                content = sql_file.read_text(encoding="utf-8")
                model_name = sql_file.stem

                # Find all var() calls
                for match in re.finditer(var_pattern, content, re.IGNORECASE):
                    var_name = match.group(1)
                    default_value = match.group(2) if match.group(2) else None

                    # Add to variables dict if not already present
                    if var_name not in variables:
                        variables[var_name] = {
                            "name": var_name,
                            "default_value": None,
                            "defined_in": None,
                            "used_in": [],
                        }

                    # Add default value if found in model
                    if default_value and not variables[var_name]["default_value"]:
                        variables[var_name]["default_value"] = default_value

                    # Track usage
                    if var_name not in usage:
                        usage[var_name] = []
                    if model_name not in usage[var_name]:
                        usage[var_name].append(model_name)

                    variables[var_name]["used_in"].append(model_name)

                # Find variables in if statements
                for match in re.finditer(if_pattern, content, re.IGNORECASE | re.DOTALL):
                    var_name = match.group(1)

                    if var_name not in variables:
                        variables[var_name] = {
                            "name": var_name,
                            "default_value": None,
                            "defined_in": None,
                            "used_in": [],
                        }

                    if var_name not in usage:
                        usage[var_name] = []
                    if model_name not in usage[var_name]:
                        usage[var_name].append(model_name)

                    variables[var_name]["used_in"].append(model_name)

            except Exception as e:
                logger.warning(f"Error extracting variables from {rel_path}: {e}")

        # Update variables with usage information
        for var_name, var_info in variables.items():
            var_info["used_in"] = usage.get(var_name, [])

        logger.info(f"Extracted {len(variables)} variables")
        return {
            "variables": variables,
            "usage": usage,
        }

    def get_variable_conversion_info(
        self, variable_name: str, conversion_log: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Get conversion information for a variable.

        Args:
            variable_name: Name of the variable
            conversion_log: Conversion log from model converter

        Returns:
            Dictionary with conversion information:
            - converted_to: How the variable was converted (e.g., "@variable:default")
            - models: List of models where it was converted
        """
        conversion_info = {
            "converted_to": [],
            "models": [],
        }

        for log_entry in conversion_log:
            model_name = log_entry.get("model")
            warnings = log_entry.get("warnings", [])

            # Check if this variable was mentioned in warnings
            for warning in warnings:
                if variable_name in warning and model_name not in conversion_info["models"]:
                    conversion_info["models"].append(model_name)

        return conversion_info
