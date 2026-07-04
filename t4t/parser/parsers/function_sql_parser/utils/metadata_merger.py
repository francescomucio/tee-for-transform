"""
Metadata merging utilities for function SQL parsing.
"""

from typing import Any

from t4t.parser.shared.exceptions import FunctionMetadataError
from t4t.parser.shared.function_utils import validate_function_metadata_consistency
from t4t.typing.metadata import FunctionMetadata


class MetadataMerger:
    """Merges SQL-extracted metadata with Python metadata file."""

    @staticmethod
    def merge(sql_metadata: dict[str, Any], python_metadata: dict[str, Any]) -> FunctionMetadata:
        """
        Merge SQL-extracted metadata with Python metadata file.

        Args:
            sql_metadata: Metadata extracted from SQL
            python_metadata: Metadata from Python file

        Returns:
            Merged function metadata

        Raises:
            FunctionMetadataError: If metadata validation fails
        """
        # Validate consistency first
        try:
            validate_function_metadata_consistency(sql_metadata, python_metadata)
        except FunctionMetadataError as e:
            raise FunctionMetadataError(
                f"Metadata validation failed for function '{sql_metadata.get('function_name', 'unknown')}': {e}"
            ) from e

        # Start with SQL metadata
        merged = sql_metadata.copy()

        # Merge other fields
        for key in [
            "description",
            "function_type",
            "parameters",
            "return_type",
            "return_table_schema",
            "schema",
            "deterministic",
            "tests",
            "tags",
            "object_tags",
        ]:
            if key in python_metadata and python_metadata[key] is not None:
                # For lists/dicts, prefer Python metadata if provided
                if key in ["parameters", "tests", "tags", "object_tags"]:
                    if python_metadata[key]:
                        merged[key] = python_metadata[key]
                else:
                    merged[key] = python_metadata[key]

        # Ensure required fields
        merged.setdefault("function_type", "scalar")
        merged.setdefault("tags", [])
        merged.setdefault("object_tags", {})
        merged.setdefault("tests", [])

        return merged
