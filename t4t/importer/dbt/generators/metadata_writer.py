"""
Metadata file writer for t4t models.

Writes Python metadata files in t4t format.
"""

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def write_metadata_file(
    target_file: Path, metadata: dict[str, Any], table_name: str | None = None
) -> None:
    """
    Write a Python metadata file in t4t format.

    Args:
        target_file: Path where the metadata file should be written
        metadata: t4t metadata dictionary
        table_name: Final table name (schema.table format) - will be added to metadata if provided
    """
    # Generate Python file content
    lines = [
        "# Model metadata converted from dbt",
        "from t4t.typing.metadata import ModelMetadata",
        "",
        "metadata: ModelMetadata = {",
    ]

    # Add table_name first (if provided)
    if table_name:
        table_name_escaped = _escape_string(table_name)
        lines.append(f'    "table_name": "{table_name_escaped}",')

    # Add description (or TODO if missing)
    if "description" in metadata and metadata["description"]:
        desc = _escape_string(metadata["description"])
        lines.append(f'    "description": "{desc}",')
    else:
        # Add TODO comment for missing description
        lines.append('    "description": "TODO: Add model description",')

    # Add materialization
    if "materialization" in metadata:
        lines.append(f'    "materialization": "{metadata["materialization"]}",')

    # Add schema
    if "schema" in metadata and metadata["schema"]:
        lines.append('    "schema": [')
        for col in metadata["schema"]:
            lines.append("        {")
            lines.append(f'            "name": "{col["name"]}",')
            lines.append(f'            "datatype": "{col.get("datatype", "string")}",')
            if "description" in col and col["description"]:
                desc = _escape_string(col["description"])
                lines.append(f'            "description": "{desc}",')
            if "tests" in col and col["tests"]:
                tests_str = _format_tests(col["tests"])
                lines.append(f'            "tests": {tests_str},')
            lines.append("        },")
        lines.append("    ],")

    # Add tests
    if "tests" in metadata and metadata["tests"]:
        tests_str = _format_tests(metadata["tests"])
        lines.append(f'    "tests": {tests_str},')

    # Add incremental config
    if "incremental" in metadata:
        lines.append('    "incremental": {')
        inc = metadata["incremental"]
        lines.append(f'        "strategy": "{inc["strategy"]}",')
        if "append" in inc:
            lines.append('        "append": {')
            lines.append(
                f'            "filter_column": "{inc["append"].get("filter_column", "updated_at")}",'
            )
            lines.append("        },")
        if "merge" in inc:
            lines.append('        "merge": {')
            lines.append(f'            "unique_key": {inc["merge"].get("unique_key", [])},')
            lines.append(
                f'            "filter_column": "{inc["merge"].get("filter_column", "updated_at")}",'
            )
            lines.append("        },")
        lines.append("    },")

    lines.append("}")

    # Write file with newline at end
    content = "\n".join(lines) + "\n"
    target_file.write_text(content, encoding="utf-8")


def _escape_string(s: str) -> str:
    """Escape string for Python string literal."""
    return s.replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")


def _format_tests(tests: list[Any]) -> str:
    """Format test list as Python list literal."""
    if not tests:
        return "[]"

    test_strs = []
    for test in tests:
        if isinstance(test, str):
            test_strs.append(f'"{test}"')
        elif isinstance(test, dict):
            # Format as dict
            parts = [f'"name": "{test.get("name", "")}"']
            if "params" in test:
                import json

                parts.append(f'"params": {json.dumps(test["params"])}')
            if "severity" in test:
                parts.append(f'"severity": "{test["severity"]}"')
            test_strs.append("{" + ", ".join(parts) + "}")
        else:
            test_strs.append(f'"{str(test)}"')

    return "[" + ", ".join(test_strs) + "]"
