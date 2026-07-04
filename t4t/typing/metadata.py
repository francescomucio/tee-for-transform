"""
Type definitions for SQL model metadata.
"""

from typing import Any, Literal, NotRequired, TypedDict

# Data type definitions
DataType = Literal[
    "string",
    "number",
    "integer",
    "float",
    "boolean",
    "timestamp",
    "date",
    "time",
    "json",
    "array",
    "object",
]

# Table semantic roles used by the Data Model view and default-test injection.
TableType = Literal["fact", "dim", "lookup", "dimension"]


# FK declaration used to express which dimension PK a fact column joins to.
class FKReference(TypedDict):
    table: str  # fully-qualified table name, e.g. "dwh.dim_date"
    column: str  # PK column in the referenced dimension, e.g. "date_id"


class HierarchyLevel(TypedDict):
    level_number: int
    name: str
    # Column carrying this level label/name in the dimension table.
    column: str
    # PK (surrogate key or join key) for this hierarchy level (optional but required by rules).
    primary_key: NotRequired[str]
    description: NotRequired[str]
    # Additional columns belonging to this level (attributes).
    columns: NotRequired[list[str]]


class HierarchyDefinition(TypedDict):
    # e.g. "Fixed-Depth Hierarchy"
    type: NotRequired[str]
    levels: list[HierarchyLevel]


class ConformedDimensionRef(TypedDict):
    """
    Declares that this physical dimension model implements a grain of a conformed dimension.

    Registers ``{logical}.{level}`` → this table in the auto-built dimension registry,
    overriding keys inferred only from hierarchy level names on another table
    (e.g. ``dim_month`` for ``date.month`` while ``dim_date`` owns the date hierarchy).
    """

    logical: str
    level: str


# Materialization types
MaterializationType = Literal["table", "view", "incremental", "scd2"]

# Incremental strategy types
IncrementalStrategy = Literal["append", "merge", "delete_insert"]

# on_schema_change options (OTS 0.2.1)
OnSchemaChange = Literal[
    "fail",  # Default - fail on schema changes
    "ignore",  # Ignore schema differences, proceed anyway
    "append_new_columns",  # Add new columns only
    "sync_all_columns",  # Add new, remove missing columns
    "full_refresh",  # Drop and recreate with full query
    "full_incremental_refresh",  # Drop, recreate, then run incremental in chunks
    "recreate_empty",  # Drop and recreate as empty table
]

# Function types
FunctionType = Literal["scalar", "aggregate", "table"]

# Test names for columns
ColumnTestName = Literal[
    "not_null",
    "unique",
    "primary_key",
    "accepted_values",
    "relationships",
    "expression",
    "custom",
]

# Test names for models
ModelTestName = Literal[
    "row_count_gt_0",
    "unique",
    "freshness",
    "hierarchy_no_split",
    "level_uniqueness",
    "custom",
]


# Test definition can be a simple string name or a dict with name/params/severity
TestDefinition = (
    str  # Simple test name like "not_null"
    | dict[str, Any]  # Dict with "name"/"test", optional "params", and optional "severity"
)


class ColumnDefinition(TypedDict):
    """Type definition for a column in the schema."""

    name: str
    datatype: DataType
    description: NotRequired[str | None]
    # Tests can be simple strings or dicts with parameters and severity
    tests: NotRequired[list[ColumnTestName | dict[str, Any]]]
    # Declared FK-style relationship metadata used by Data Model view.
    # Intended for fact columns joining to dimension PK columns.
    fk_to: NotRequired[FKReference | None]

    # Simplified FK metadata: logical dimension name, optionally with hierarchy grain.
    # Registry is auto-built from models with table_type dim/dimension or dim_* names.
    # Examples: "date" -> dim_date; "date.month" -> same dim if Month is a hierarchy level.
    dimension: NotRequired[str | None]
    # If True, system will automatically calculate IDs using MAX(id) + ROW_NUMBER()
    auto_incremental: NotRequired[bool]


class IncrementalAppendConfig(TypedDict):
    """Configuration for append-only incremental strategy."""

    filter_column: str
    start_value: NotRequired[str | None]  # "auto" for max(filter_column) pattern, or specific value
    destination_filter_column: NotRequired[
        str | None
    ]  # Column name in target table (if different from filter_column)
    lookback: NotRequired[str | None]  # e.g., "7 days", "1 week"


class IncrementalMergeConfig(TypedDict):
    """Configuration for merge incremental strategy."""

    unique_key: list[str]
    filter_column: str
    start_value: NotRequired[str | None]  # "auto" for max(filter_column) pattern, or specific value
    destination_filter_column: NotRequired[
        str | None
    ]  # Column name in target table (if different from filter_column)
    lookback: NotRequired[str | None]  # e.g., "7 days", "1 week"


class IncrementalDeleteInsertConfig(TypedDict):
    """Configuration for delete+insert incremental strategy."""

    where_condition: str  # SQL WHERE clause to identify records to delete
    filter_column: str
    start_value: NotRequired[str | None]  # "auto" for max(filter_column) pattern, or specific value
    destination_filter_column: NotRequired[
        str | None
    ]  # Column name in target table (if different from filter_column)
    lookback: NotRequired[str | None]  # e.g., "7 days", "1 week"


class FullIncrementalRefreshParameter(TypedDict):
    """Parameter configuration for full_incremental_refresh chunking (OTS 0.2.1)."""

    name: str  # Parameter name (matches placeholder in query, e.g., "@start_date", "@end_date")
    start_value: str  # Initial value for the parameter
    end_value: str  # End condition: hardcoded value (e.g., "2025-12-31") or expression evaluated against source table (e.g., "max(event_date)")
    step: str  # Increment step: SQL interval (e.g., "INTERVAL 1 DAY") or numeric value


class FullIncrementalRefreshConfig(TypedDict):
    """Configuration for full_incremental_refresh on_schema_change behavior (OTS 0.2.1)."""

    parameters: list[FullIncrementalRefreshParameter]


class IncrementalConfig(TypedDict):
    """Configuration for incremental materialization strategies."""

    strategy: IncrementalStrategy
    on_schema_change: NotRequired[OnSchemaChange]  # Default: "fail" (OTS 0.2.1)
    append: NotRequired[IncrementalAppendConfig | None]
    merge: NotRequired[IncrementalMergeConfig | None]
    delete_insert: NotRequired[IncrementalDeleteInsertConfig | None]


class ModelMetadata(TypedDict):
    """
    Unified type definition for model metadata.

    Works for both user input (from Python files) and parsed/validated metadata.
    """

    description: NotRequired[str | None]
    schema: NotRequired[list[ColumnDefinition] | None]
    partitions: NotRequired[list[str] | None]
    materialization: NotRequired[MaterializationType | None]
    # Semantic table role (used by the Data Model view; optional if inferable from prefix).
    table_type: NotRequired[TableType]
    # If true, force inclusion in the Data Model view even if not dim/fact/lookup.
    data_model: NotRequired[bool]
    # Optional dimension hierarchy definition.
    hierarchy: NotRequired[HierarchyDefinition]
    # Map this table to a conformed logical dimension + grain (see ConformedDimensionRef).
    conformed_dimension: NotRequired[ConformedDimensionRef]
    # Disable auto-injected default tests.
    # - True disables all default tests
    # - list[str] disables only the listed default test names
    disable_default_tests: NotRequired[list[str] | bool]
    # Tests can be simple strings or dicts with parameters and severity
    tests: NotRequired[list[ModelTestName | dict[str, Any]] | None]
    incremental: NotRequired[IncrementalConfig | None]
    scd2_details: NotRequired[dict[str, Any] | None]  # For SCD2 materialization
    indexes: NotRequired[list[dict[str, Any]] | None]  # Explicit index definitions
    full_incremental_refresh: NotRequired[
        FullIncrementalRefreshConfig | None
    ]  # For full_incremental_refresh on_schema_change (OTS 0.2.1)


# Function-specific types


class FunctionParameter(TypedDict):
    """Type definition for a function parameter."""

    name: str
    type: str  # SQL type string (e.g., "FLOAT", "VARCHAR(255)", "INTEGER")
    description: NotRequired[str | None]
    default: NotRequired[str | None]  # Default value as string
    mode: NotRequired[Literal["IN", "OUT", "INOUT"]]  # Parameter mode (for some databases)


class FunctionMetadata(TypedDict):
    """
    Unified type definition for function metadata.

    Works for both user input (from Python files) and parsed/validated metadata.
    """

    function_name: str
    description: NotRequired[str | None]
    function_type: NotRequired[FunctionType]  # "scalar", "aggregate", "table" (default: "scalar")
    language: NotRequired[str | None]  # "sql", "python", "javascript", etc.
    parameters: NotRequired[list[FunctionParameter] | None]
    return_type: NotRequired[str | None]  # SQL type string for scalar/aggregate functions
    return_table_schema: NotRequired[list[ColumnDefinition] | None]  # For table-valued functions
    schema: NotRequired[str | None]  # Schema name
    deterministic: NotRequired[bool | None]  # Whether function is deterministic
    # Tests can be simple strings or dicts with parameters and severity
    tests: NotRequired[list[str | dict[str, Any]] | None]
    # Tags (dbt-style, list of strings)
    tags: NotRequired[list[str] | None]
    # Object tags (database-style, key-value pairs)
    object_tags: NotRequired[dict[str, str] | None]
    # Source SQL dialect for conversion (e.g., "postgres", "mysql", "generic")
    # If not specified, uses project config source_sql_dialect or "generic" as default
    source_sql_dialect: NotRequired[str | None]


# OTS-specific types for the Open Transformation Specification


class OTSTarget(TypedDict):
    """Target configuration for an OTS Module."""

    database: str
    schema: str
    sql_dialect: NotRequired[str | None]
    connection_profile: NotRequired[str | None]


class OTSTransformation(TypedDict):
    """Single transformation definition in an OTS Module."""

    transformation_id: str
    description: NotRequired[str | None]
    transformation_type: NotRequired[
        str | None
    ]  # "sql" (default), future: "python", "pyspark", "r"
    sql_dialect: NotRequired[str | None]
    code: dict[
        str, Any
    ]  # Type-based structure: {"sql": {"original_sql": ..., "resolved_sql": ..., "source_tables": [...]}}
    schema: NotRequired[dict[str, Any] | None]
    materialization: NotRequired[dict[str, Any] | None]
    tests: NotRequired[dict[str, Any] | None]
    metadata: dict[str, Any]


class OTSFunction(TypedDict):
    """Single function definition in an OTS Module (OTS 0.2.0+)."""

    function_id: str  # Fully qualified function name (e.g., "schema.function_name")
    description: NotRequired[str | None]
    function_type: FunctionType  # "scalar", "aggregate", "table"
    language: str  # "sql", "python", "javascript", etc.
    parameters: NotRequired[list[FunctionParameter]]
    return_type: NotRequired[str | None]  # For scalar/aggregate functions
    return_table_schema: NotRequired[list[ColumnDefinition] | None]  # For table functions
    deterministic: NotRequired[
        bool | None
    ]  # Whether function is deterministic (same inputs = same outputs)
    code: dict[str, Any]  # Type-based structure with generic_sql and database_specific
    dependencies: NotRequired[dict[str, list[str]]]  # {"functions": [], "tables": []}
    metadata: dict[str, Any]  # Includes tags, object_tags, file_path, etc.


class OTSModule(TypedDict):
    """Complete OTS Module structure."""

    ots_version: str
    module_name: str
    module_description: NotRequired[str | None]
    version: NotRequired[str | None]
    tags: NotRequired[list[str] | None]
    test_library_path: NotRequired[str | None]
    target: OTSTarget
    transformations: list[OTSTransformation]
    functions: NotRequired[list[OTSFunction] | None]  # NEW in OTS 0.2.0
