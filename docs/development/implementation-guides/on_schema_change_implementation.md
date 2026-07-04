# Implementation Guide: on_schema_change for Incremental Materialization

## Overview

This guide outlines how to implement `on_schema_change` support for incremental materialization in t4t. The feature allows automatic handling of schema differences between transformation output and existing target tables.

## Architecture Overview

The implementation should follow this flow:

```
1. Execute transformation query to infer output schema
2. Compare output schema with existing table schema (if table exists)
3. Apply schema changes based on on_schema_change setting
4. Execute incremental materialization strategy
```

## Implementation Steps

### Step 1: Update Type Definitions

**File:** `tee-for-transform/tee/typing/metadata.py`

Add `on_schema_change` to the incremental config types:

```python
# Add new type for on_schema_change values (matches OTS 0.2.1)
OnSchemaChange = Literal[
    "fail",                    # Default - fail on schema changes
    "ignore",                  # Ignore schema differences, proceed anyway
    "append_new_columns",      # Add new columns only
    "sync_all_columns",         # Add new, remove missing columns
    "full_refresh",            # Drop and recreate with full query
    "full_incremental_refresh", # Drop, recreate, then run incremental in chunks
    "recreate_empty"           # Drop and recreate as empty table
]

# Update IncrementalConfig
class IncrementalConfig(TypedDict):
    """Configuration for incremental materialization strategies."""
    strategy: IncrementalStrategy
    on_schema_change: NotRequired[OnSchemaChange]  # NEW - default: "fail"
    append: NotRequired[IncrementalAppendConfig | None]
    merge: NotRequired[IncrementalMergeConfig | None]
    delete_insert: NotRequired[IncrementalDeleteInsertConfig | None]
```

**Note**: Default value is `"fail"` if not specified. The `"ignore"` option is available for backward compatibility and manual schema management.

### Step 2: Create Schema Comparison Module

**New File:** `tee-for-transform/tee/engine/materialization/schema_comparator.py`

This module will:
- Infer schema from SQL query output
- Compare schemas between query output and existing table
- Generate DDL statements for schema changes

```python
"""
Schema comparison and change detection for incremental materialization.
"""

import logging
from typing import Any

from t4t.adapters.base.core import DatabaseAdapter

logger = logging.getLogger(__name__)


class SchemaComparator:
    """Compares transformation output schema with existing table schema."""
    
    def __init__(self, adapter: DatabaseAdapter):
        self.adapter = adapter
    
    def infer_query_schema(self, sql_query: str) -> list[dict[str, Any]]:
        """
        Infer schema from SQL query output.
        
        Returns:
            List of column definitions: [{"name": "col1", "type": "VARCHAR"}, ...]
        """
        # Implementation approach:
        # 1. Execute LIMIT 0 query to get schema without data
        # 2. Use adapter's query result metadata
        # 3. Or use DESCRIBE/EXPLAIN on the query
        pass
    
    def get_table_schema(self, table_name: str) -> list[dict[str, Any]]:
        """
        Get schema from existing table.
        
        Returns:
            List of column definitions: [{"name": "col1", "type": "VARCHAR"}, ...]
        """
        # Use adapter.get_table_info() or adapter.get_table_columns()
        # Different adapters may need different approaches
        pass
    
    def compare_schemas(
        self, 
        query_schema: list[dict[str, Any]], 
        table_schema: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Compare two schemas and identify differences.
        
        Returns:
            {
                "new_columns": [...],  # Columns in query but not in table
                "missing_columns": [...],  # Columns in table but not in query
                "type_mismatches": [...],  # Same column, different type
                "has_changes": bool
            }
        """
        pass
```

### Step 3: Create Schema Change Handler

**New File:** `tee-for-transform/tee/engine/materialization/schema_change_handler.py`

This module will:
- Handle the four `on_schema_change` behaviors
- Generate and execute DDL statements
- Provide database-specific implementations

```python
"""
Handles schema changes based on on_schema_change configuration.
"""

import logging
from typing import Any

from t4t.adapters.base.core import DatabaseAdapter
from t4t.typing.metadata import OnSchemaChange

logger = logging.getLogger(__name__)


class SchemaChangeHandler:
    """Handles schema changes for incremental materialization."""
    
    def __init__(self, adapter: DatabaseAdapter):
        self.adapter = adapter
    
    def handle_schema_changes(
        self,
        table_name: str,
        query_schema: list[dict[str, Any]],
        table_schema: list[dict[str, Any]],
        on_schema_change: OnSchemaChange,
    ) -> None:
        """
        Handle schema changes based on on_schema_change setting.
        
        Args:
            table_name: Target table name
            query_schema: Schema from transformation output
            table_schema: Schema from existing table
            on_schema_change: Behavior setting
        """
        from .schema_comparator import SchemaComparator
        
        comparator = SchemaComparator(self.adapter)
        differences = comparator.compare_schemas(query_schema, table_schema)
        
        if not differences["has_changes"]:
            logger.debug(f"No schema changes detected for {table_name}")
            return
        
        if on_schema_change == "fail":
            raise ValueError(
                f"Schema changes detected for {table_name} but on_schema_change='fail'. "
                f"New columns: {differences['new_columns']}, "
                f"Missing columns: {differences['missing_columns']}"
            )
        
        if on_schema_change == "ignore":
            logger.info(f"Ignoring schema changes for {table_name}")
            return
        
        if on_schema_change == "append_new_columns":
            self._append_new_columns(table_name, differences["new_columns"])
        
        elif on_schema_change == "sync_all_columns":
            self._sync_all_columns(
                table_name, 
                differences["new_columns"],
                differences["missing_columns"]
            )
        
        elif on_schema_change == "full_refresh":
            self._full_refresh(table_name, sql_query)
        
        elif on_schema_change == "full_incremental_refresh":
            self._full_incremental_refresh(table_name, sql_query, config)
        
        elif on_schema_change == "recreate_empty":
            self._recreate_empty(table_name, query_schema)
    
    def _append_new_columns(
        self, 
        table_name: str, 
        new_columns: list[dict[str, Any]]
    ) -> None:
        """Add new columns to existing table."""
        for column in new_columns:
            self._add_column(table_name, column)
    
    def _sync_all_columns(
        self,
        table_name: str,
        new_columns: list[dict[str, Any]],
        missing_columns: list[dict[str, Any]],
    ) -> None:
        """Sync all columns: add new, remove missing."""
        # Add new columns
        for column in new_columns:
            self._add_column(table_name, column)
        
        # Remove missing columns (with warning)
        if missing_columns:
            logger.warning(
                f"sync_all_columns will remove columns from {table_name}: {missing_columns}"
            )
            for column in missing_columns:
                self._drop_column(table_name, column)
    
    def _add_column(self, table_name: str, column: dict[str, Any]) -> None:
        """Add a column to a table (database-specific)."""
        # Delegate to adapter for database-specific DDL
        if hasattr(self.adapter, "add_column"):
            self.adapter.add_column(table_name, column)
        else:
            # Fallback: generate ALTER TABLE ADD COLUMN
            self._generate_add_column_ddl(table_name, column)
    
    def _drop_column(self, table_name: str, column: dict[str, Any]) -> None:
        """Drop a column from a table (database-specific)."""
        # Delegate to adapter for database-specific DDL
        if hasattr(self.adapter, "drop_column"):
            self.adapter.drop_column(table_name, column["name"])
        else:
            # Fallback: generate ALTER TABLE DROP COLUMN
            self._generate_drop_column_ddl(table_name, column["name"])
    
    def _generate_add_column_ddl(
        self, 
        table_name: str, 
        column: dict[str, Any]
    ) -> str:
        """Generate ALTER TABLE ADD COLUMN DDL (database-specific)."""
        # Use adapter's SQL dialect to generate correct syntax
        pass
    
    def _generate_drop_column_ddl(self, table_name: str, column_name: str) -> str:
        """Generate ALTER TABLE DROP COLUMN DDL (database-specific)."""
        pass
```

### Step 4: Integrate into Incremental Executor

**File:** `tee-for-transform/tee/engine/materialization/incremental_executor.py`

Add schema change handling before executing strategies:

```python
def execute_append_strategy(
    self,
    model_name: str,
    sql_query: str,
    config: IncrementalAppendConfig,
    adapter: DatabaseAdapter,
    table_name: str,
    variables: dict[str, Any] | None = None,
    on_schema_change: OnSchemaChange | None = "fail",  # NEW - default: "fail"
) -> None:
    """Execute append-only incremental strategy."""
    
    # NEW: Handle schema changes if table exists
    # Default to "fail" if not specified
    if on_schema_change is None:
        on_schema_change = "fail"
    
    if adapter.table_exists(table_name) and on_schema_change:
        from .schema_change_handler import SchemaChangeHandler
        from .schema_comparator import SchemaComparator
        
        handler = SchemaChangeHandler(adapter)
        comparator = SchemaComparator(adapter)
        
        query_schema = comparator.infer_query_schema(sql_query)
        table_schema = comparator.get_table_schema(table_name)
        
        handler.handle_schema_changes(
            table_name, 
            query_schema, 
            table_schema, 
            on_schema_change
        )
    
    # Continue with existing append logic...
    # ... rest of the method
```

Apply the same pattern to `execute_merge_strategy` and `execute_delete_insert_strategy`.

### Step 5: Update Materialization Handler

**File:** `tee-for-transform/tee/engine/materialization/materialization_handler.py`

Pass `on_schema_change` to executor methods:

```python
def _execute_incremental_materialization(
    self, table_name: str, sql_query: str, metadata: dict[str, Any] | None = None
) -> None:
    """Execute incremental materialization using the universal state manager."""
    # ... existing code ...
    
    # Extract on_schema_change (default: "fail" per OTS 0.2.1)
    on_schema_change = incremental_config.get("on_schema_change", "fail")
    
    # ... existing strategy execution ...
    
    if strategy == "append":
        # ... existing code ...
        executor.execute_append_strategy(
            table_name,
            sql_query,
            append_config,
            self.adapter,
            table_name,
            self.variables,
            on_schema_change=on_schema_change,  # NEW
        )
    # ... same for merge and delete_insert ...
```

### Step 6: Update dbt Importer

**File:** `tee-for-transform/tee/importer/dbt/converters/metadata_converter.py`

Update `_convert_incremental_config` to convert `on_schema_change` instead of warning:

```python
def _convert_incremental_config(
    self, config: dict[str, Any]
) -> tuple[dict[str, Any] | None, list[str]]:
    """Convert dbt incremental config to t4t incremental config."""
    # ... existing code ...
    
    on_schema_change = config.get("on_schema_change")
    
    result: dict[str, Any] = {"strategy": t4t_strategy}
    
    # NEW: Convert on_schema_change instead of warning
    if on_schema_change:
        # dbt uses same values: "ignore", "append_new_columns", "sync_all_columns", "fail"
        result["on_schema_change"] = on_schema_change
    
    # Remove the warning code for on_schema_change
    
    # ... rest of the method ...
```

### Step 7: Add Database Adapter Methods (Optional but Recommended)

**File:** `tee-for-transform/tee/adapters/base/core.py`

Add optional methods to the base adapter interface:

```python
@abstractmethod
def add_column(self, table_name: str, column: dict[str, Any]) -> None:
    """
    Add a column to an existing table.
    
    Args:
        table_name: Name of the table
        column: Column definition with "name" and "type" keys
    """
    pass

@abstractmethod
def drop_column(self, table_name: str, column_name: str) -> None:
    """
    Drop a column from an existing table.
    
    Args:
        table_name: Name of the table
        column_name: Name of the column to drop
    """
    pass
```

Then implement these in each adapter (Snowflake, DuckDB, PostgreSQL, BigQuery, etc.).

## Database-Specific Considerations

### Snowflake
- Supports `ALTER TABLE ADD COLUMN`
- Supports `ALTER TABLE DROP COLUMN`
- Type changes may require special handling

### PostgreSQL
- Supports `ALTER TABLE ADD COLUMN`
- Supports `ALTER TABLE DROP COLUMN` (with CASCADE if needed)
- Type changes may require explicit casting

### BigQuery
- Supports `ALTER TABLE ADD COLUMN`
- Supports `ALTER TABLE DROP COLUMN` (with limitations)
- Type changes are more restricted

### DuckDB
- Supports schema modifications
- May have different syntax for ALTER TABLE

## Testing Strategy

1. **Unit Tests:**
   - Schema comparison logic
   - Schema change handler for each behavior
   - DDL generation

2. **Integration Tests:**
   - Full incremental flow with schema changes
   - Each `on_schema_change` behavior
   - Database-specific implementations

3. **Test Cases:**
   - New columns added
   - Columns removed
   - Type mismatches
   - No changes (should skip)
   - `fail` behavior raises error
   - `append_new_columns` adds only new columns
   - `sync_all_columns` adds and removes columns

## Implementation Order

1. ✅ Update type definitions
2. ✅ Create schema comparison module
3. ✅ Create schema change handler
4. ✅ Integrate into incremental executor
5. ✅ Update materialization handler
6. ✅ Update dbt importer
7. ✅ Implement database adapter methods
8. ✅ Add comprehensive tests
9. ✅ Update documentation

## Example Usage

After implementation, users can use it like this:

```python
@model(
    table_name="marts.orders",
    materialization="incremental",
    incremental={
        "strategy": "append",
        "on_schema_change": "append_new_columns",  # NEW
        "append": {
            "filter_column": "created_at",
            "start_value": "2024-01-01"
        }
    }
)
def orders():
    return "SELECT order_id, customer_id, total, created_at, new_column FROM ..."
```

## Notes

- Default behavior should be `"ignore"` for backward compatibility
- Schema inference from queries may require executing LIMIT 0 queries
- Some databases may not support all operations (e.g., dropping columns)
- Type changes may need separate handling or manual intervention
- Consider performance implications of schema comparison queries


