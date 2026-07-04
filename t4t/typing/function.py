"""
Type definitions for functions.
"""

from typing import Any, NotRequired, TypedDict

from .metadata import FunctionMetadata


class FunctionCodeSQL(TypedDict):
    """SQL code structure within a function's code field."""

    original_sql: str
    resolved_sql: str
    operation_type: str
    source_tables: list[str]
    source_functions: list[str]


class FunctionCode(TypedDict):
    """Code structure for a function."""

    sql: FunctionCodeSQL


class FunctionMetadataInfo(TypedDict):
    """Function metadata structure (wrapper around FunctionMetadata)."""

    function_name: str
    description: str | None
    function_type: str  # "scalar", "aggregate", "table"
    language: str | None
    parameters: list[dict[str, Any]]
    return_type: str | None
    return_table_schema: list[dict[str, Any]] | None
    schema: str | None
    deterministic: bool
    tests: list[str | dict[str, Any]]
    tags: list[str]
    object_tags: dict[str, str]
    metadata: dict[str, Any] | FunctionMetadata
    file_path: NotRequired[str]


class Function(TypedDict):
    """
    Type definition for a function.

    This represents the standardized structure of a function after parsing,
    whether it comes from a SQL file, Python file, or OTS module.
    """

    code: FunctionCode | None
    function_metadata: FunctionMetadataInfo
    function_hash: str
    needs_evaluation: NotRequired[bool]
    evaluation_error: NotRequired[str]
    file_path: NotRequired[str]


# Backward compatibility alias (deprecated, use Function instead)
ParsedFunction = Function
