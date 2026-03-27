"""
Type definitions for models.
"""

from typing import Any, NotRequired, TypedDict

from .metadata import ModelMetadata


class ModelCodeSQL(TypedDict):
    """SQL code structure within a model's code field."""

    original_sql: str
    resolved_sql: str
    operation_type: str
    source_tables: list[str]
    source_functions: list[str]


class ModelCode(TypedDict):
    """Code structure for a model."""

    sql: ModelCodeSQL


class ModelMetadataInfo(TypedDict):
    """Model metadata structure (wrapper around ModelMetadata)."""

    table_name: str
    function_name: str | None
    description: str | None
    variables: list[str]
    metadata: dict[str, Any] | ModelMetadata
    file_path: NotRequired[str]


class Model(TypedDict):
    """
    Type definition for a model.

    This represents the standardized structure of a model after parsing,
    whether it comes from a SQL file, Python file, or OTS module.
    """

    code: ModelCode | None
    model_metadata: ModelMetadataInfo
    sqlglot_hash: str
    needs_evaluation: NotRequired[bool]
    evaluation_error: NotRequired[str]


# Backward compatibility alias (deprecated, use Model instead)
ParsedModel = Model
