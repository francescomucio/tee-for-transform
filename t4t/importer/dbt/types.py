"""
Type definitions for dbt importer.

Provides TypedDict classes for type-safe data structures.
"""

from typing import Any, TypedDict


class ConversionLogEntry(TypedDict, total=False):
    """Entry in conversion log for a single model/test/macro."""

    model: str  # Model name
    status: str  # "converted", "python_model", "error", "unconvertible"
    table_name: str  # Final table name (schema.table)
    warnings: list[str]  # List of warning messages
    error: str  # Error message (if status is "error")
    reason: str  # Reason for unconvertible status
    udf_name: str  # UDF name (for macros)
    macro: str  # Macro name
    rel_path: str  # Relative path (for tests)
    target_file: str  # Target file path (for tests)
    converted: bool  # Whether conversion succeeded (for tests)
    skipped: bool  # Whether test was skipped (for tests)
    errors: list[str]  # List of errors (for tests)


class ConversionResults(TypedDict):
    """Results from model conversion."""

    converted: int
    python_models: int
    errors: int
    total: int
    conversion_log: list[ConversionLogEntry]


class MacroResults(TypedDict):
    """Results from macro conversion."""

    converted: int
    unconvertible: int
    total: int
    conversion_log: list[ConversionLogEntry]


class TestResults(TypedDict):
    """Results from test conversion."""

    converted: int
    skipped: int
    errors: int
    total: int
    conversion_log: list[ConversionLogEntry]


class SeedResults(TypedDict):
    """Results from seed conversion."""

    copied: int
    errors: int


class VariableInfo(TypedDict, total=False):
    """Information about a dbt variable."""

    default_value: str  # Default value
    defined_in: str  # Where variable is defined (dbt_project.yml or model file)
    used_in: list[str]  # List of models using this variable


class VariablesInfo(TypedDict):
    """Information about all variables."""

    variables: dict[str, VariableInfo]


class ModelMetadata(TypedDict, total=False):
    """t4t model metadata structure."""

    description: str
    materialization: str
    schema: list[dict[str, Any]]
    incremental: dict[str, Any]
    tags: list[str]
    meta: dict[str, Any]
    variables: list[str]
    dependencies: list[str]
