# on_schema_change Execution Flow

## Overview

This document explains the execution flow for `on_schema_change` functionality, including who runs the model and when schema change detection happens.

## Execution Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. User/CLI calls ExecutionEngine.execute_models()              │
└───────────────────────┬─────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. ModelExecutor.execute()                                      │
│    - Iterates through models in execution order                 │
│    - Extracts SQL query and metadata                            │
└───────────────────────┬─────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. ModelExecutor calls MaterializationHandler.materialize()     │
│    - Passes: table_name, sql_query, materialization, metadata   │
└───────────────────────┬─────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. MaterializationHandler routes based on materialization type  │
│    - If "incremental" → _execute_incremental_materialization()  │
│    - If "table" → adapter.create_table()                        │
│    - If "view" → adapter.create_view()                          │
└───────────────────────┬─────────────────────────────────────────┘
                        │
                        ▼ (for incremental)
┌─────────────────────────────────────────────────────────────────┐
│ 5. MaterializationHandler._execute_incremental_materialization()│
│    - Extracts on_schema_change from incremental_config          │
│    - Extracts full_incremental_refresh from metadata            │
│    - Creates IncrementalExecutor(state_manager)                 │
│    - Calls executor strategy method (append/merge/delete_insert)│
└───────────────────────┬─────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│ 6. IncrementalExecutor.execute_append_strategy()                │
│    (or execute_merge_strategy / execute_delete_insert_strategy) │
│                                                                 │
│    ┌─────────────────────────────────────────────────────────┐ │
│    │ IF table_exists(table_name):                             │ │
│    │   - Create SchemaComparator(adapter)                      │ │
│    │   - Create SchemaChangeHandler(adapter)                   │ │
│    │   - query_schema = comparator.infer_query_schema(sql)     │ │
│    │   - table_schema = comparator.get_table_schema(table)     │ │
│    │   - handler.handle_schema_changes(                        │ │
│    │       table_name, query_schema, table_schema,             │ │
│    │       on_schema_change, sql_query,                       │ │
│    │       full_incremental_refresh_config,                   │ │
│    │       incremental_config                                 │ │
│    │     )                                                     │ │
│    └─────────────────────────────────────────────────────────┘ │
│                                                                 │
│    - Continue with incremental execution (time filtering, etc.)│
└─────────────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│ 7. SchemaChangeHandler.handle_schema_changes()                  │
│    - Compares query_schema vs table_schema                      │
│    - Detects: new_columns, missing_columns, type_mismatches    │
│    - Routes to appropriate handler based on on_schema_change:   │
│      * "fail" → raises ValueError                                │
│      * "ignore" → logs and continues                            │
│      * "append_new_columns" → adds new columns                  │
│      * "sync_all_columns" → adds new, removes missing           │
│      * "full_refresh" → drops and recreates with full query     │
│      * "full_incremental_refresh" → drops, recreates, chunks   │
│      * "recreate_empty" → drops and recreates empty             │
└─────────────────────────────────────────────────────────────────┘
```

## Key Components

### 1. State Manager (`ModelStateManager`)

**Purpose**: Tracks execution state for incremental models

**What it stores**:
- `last_processed_value`: Last processed timestamp/value for incremental filtering
- `sql_hash`: Hash of SQL query to detect query changes
- `config_hash`: Hash of incremental config to detect config changes
- `strategy`: Which incremental strategy was used (append/merge/delete_insert)

**Used by**:
- `IncrementalExecutor.should_run_incremental()`: Decides if model should run incrementally or as full load
- `IncrementalExecutor` strategy methods: Get last processed value for time filtering

**In tests**: Created as a fixture to track state between test runs

### 2. Who Runs the Model?

**Production Flow**:
1. **User/CLI** → Calls `ExecutionEngine.execute_models()`
2. **ExecutionEngine** → Creates `ModelExecutor` and calls `execute()`
3. **ModelExecutor** → Calls `MaterializationHandler.materialize()`
4. **MaterializationHandler** → Routes to appropriate handler based on materialization type
5. **IncrementalExecutor** → Executes incremental strategy

**In Tests**:
- Tests directly call `MaterializationHandler.materialize()` to simulate model execution
- This bypasses `ModelExecutor` and `ExecutionEngine` for simplicity

### 3. Who Triggers `on_schema_change`?

**Trigger Point**: `IncrementalExecutor` strategy methods (`execute_append_strategy`, `execute_merge_strategy`, `execute_delete_insert_strategy`)

**When it triggers**:
1. **Before** incremental execution
2. **Only if** `adapter.table_exists(table_name)` returns `True`
3. **Only if** running incrementally (not full load)

**Flow**:
```python
def execute_append_strategy(...):
    # 1. Check if table exists
    if adapter.table_exists(table_name):
        # 2. Compare schemas
        handler = SchemaChangeHandler(adapter)
        comparator = SchemaComparator(adapter)
        query_schema = comparator.infer_query_schema(sql_query)
        table_schema = comparator.get_table_schema(table_name)

        # 3. Handle schema changes (this is where on_schema_change is used)
        handler.handle_schema_changes(
            table_name,
            query_schema,
            table_schema,
            on_schema_change,  # ← From incremental_config
            sql_query=sql_query,
            full_incremental_refresh_config=full_incremental_refresh_config,
            incremental_config=incremental_config,
        )

    # 4. Continue with incremental execution
    # (time filtering, append/merge/delete_insert logic)
```

## Important Notes

1. **Schema change detection happens BEFORE incremental execution**
   - This ensures schema is correct before inserting/merging data
   - If schema change handling fails (e.g., `on_schema_change="fail"`), incremental execution never happens

2. **Schema change detection only happens when**:
   - Materialization type is `"incremental"`
   - Table already exists in database
   - Model is running incrementally (not full load)

3. **State Manager is used for**:
   - Deciding if model should run incrementally vs full load
   - Getting last processed value for time filtering
   - **NOT** used for schema change detection (that's done by comparing current query schema vs existing table schema)

4. **In tests**, we manually set up state using `state_manager.update_processed_value()` to simulate a previous run, so the next run will be incremental (not full load).

## Example: Complete Flow

```python
# 1. First run (full load - no schema change check)
handler.materialize(
    "my_table",
    "SELECT id, name FROM source",
    "incremental",
    metadata={"incremental": {"strategy": "append", "append": {...}}}
)
# → Table doesn't exist → Full load → Creates table

# 2. Set up state (simulates previous run)
state_manager.update_processed_value("my_table", "2024-01-01", "append")

# 3. Second run with different schema (incremental - schema change check happens)
handler.materialize(
    "my_table",
    "SELECT id, name, email FROM source",  # Added 'email' column
    "incremental",
    metadata={
        "incremental": {
            "strategy": "append",
            "append": {...},
            "on_schema_change": "append_new_columns"  # ← Triggers schema change handling
        }
    }
)
# → Table exists → Schema change detected → Adds 'email' column → Continues with incremental
```
