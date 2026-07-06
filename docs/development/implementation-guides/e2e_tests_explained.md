# How E2E Tests for Incremental Strategies Work

## Overview

The end-to-end tests simulate the complete flow of incremental materialization with schema changes. This document explains how they work step-by-step, including the role of the state manager and when schema change detection happens.

## Test Setup (Fixtures)

### 1. `adapter` fixture
```python
@pytest.fixture
def adapter(self):
    # Creates a temporary DuckDB database file
    # Returns connected DuckDBAdapter instance
    # Cleaned up after test
```

**Purpose**: Provides a real database connection for testing (not mocks)

### 2. `state_manager` fixture
```python
@pytest.fixture
def state_manager(self):
    # Creates a temporary state database file
    # Returns ModelStateManager instance
    # Cleaned up after test
```

**Purpose**: Tracks execution state (like a real production run would)

**What it stores:**
- `last_processed_value`: Last processed timestamp for time filtering
- `sql_hash`: Hash of SQL query (to detect query changes)
- `config_hash`: Hash of incremental config (to detect config changes)
- `strategy`: Which incremental strategy was used (append/merge/delete_insert)

### 3. `handler` fixture
```python
@pytest.fixture
def handler(self, adapter, state_manager):
    return MaterializationHandler(adapter, state_manager, {})
```

**Purpose**: The main component that executes materialization

### 4. `initial_table_with_data` fixture
```python
@pytest.fixture
def initial_table_with_data(self, adapter):
    # Creates source_events table with 3 rows:
    # (1, 'event1', '2024-01-01', 100)
    # (2, 'event2', '2024-01-02', 200)
    # (3, 'event3', '2024-01-03', 300)
```

**Purpose**: Sets up source data that the model will query

## Test Flow: Step-by-Step Example

Let's trace through `test_incremental_append_with_append_new_columns_e2e`:

### Step 1: First Run (Full Load)

```python
# Step 1: Create initial table with old schema
initial_query = "SELECT event_id, event_name, event_date FROM source_events"
metadata = {
    "incremental": {
        "strategy": "append",
        "append": {"filter_column": "event_date", "start_value": "2024-01-01"},
    }
}
handler.materialize(table_name, initial_query, "incremental", metadata)
```

**What happens inside `handler.materialize()`:**

1. **MaterializationHandler** sees `materialization="incremental"`
2. Calls `_execute_incremental_materialization()`
3. **IncrementalExecutor** is created with `state_manager`
4. `should_run_incremental()` is called:
   ```python
   state = state_manager.get_model_state(table_name)  # Returns None (no state yet)
   if state is None:
       return False  # → Full load
   ```
5. Since `should_run_incremental()` returns `False`:
   - **No schema change check** (table doesn't exist yet)
   - Executes: `adapter.create_table(table_name, sql_query, metadata)`
   - Creates table with 3 columns: `event_id`, `event_name`, `event_date`
   - Inserts all 3 rows from source_events
6. **State is saved** (after full load):
   ```python
   state_manager.update_processed_value(table_name, current_time, "append")
   ```
   **Important Note**:
   - `update_processed_value()` only updates `last_processed_value`
   - **CRITICAL**: `update_processed_value()` requires state to exist first (line 190-192)
   - If no state exists, it just logs a warning and returns (does nothing!)
   - In tests, we bypass `ModelExecutor.save_model_state()`, so state might not be created
   - This means after Step 1, there might be NO state at all

**Result**: Table `target_events` exists with:
- Schema: `event_id`, `event_name`, `event_date` (3 columns)
- Data: 3 rows
- **State**: **NO STATE CREATED** (because `update_processed_value()` requires state to exist first, and we bypass `ModelExecutor.save_model_state()`)

### Step 2: Set Up State for Incremental Run

```python
# Step 2: Set up state for incremental run
from datetime import UTC, datetime
current_time = datetime.now(UTC).isoformat()
state_manager.update_processed_value(table_name, current_time, "append")
```

**What this does:**
- Updates the `last_processed_value` in the existing state
- **Important**: `update_processed_value()` preserves the existing `sql_hash` and `config_hash` from Step 1
- This ensures state is complete for the next run

**Why this is needed:**
- After Step 1, state exists but might not have proper `last_processed_value`
- This ensures the state is complete for the next incremental run
- **Note**: If the SQL query changes in Step 3, the SQL hash will be different, which would normally trigger a full load. However, in our test, we're testing schema change handling, which can happen in different scenarios.

### Step 3: Second Run with Schema Change

```python
# Step 3: Run with new schema (adds 'value' column)
new_query = "SELECT event_id, event_name, event_date, value FROM source_events"
metadata["incremental"]["on_schema_change"] = "append_new_columns"

handler.materialize(table_name, new_query, "incremental", metadata)
```

**What happens inside `handler.materialize()`:**

1. **MaterializationHandler** calls `_execute_incremental_materialization()`
2. **IncrementalExecutor** is created
3. `should_run_incremental()` is called:
   ```python
   state = state_manager.get_model_state(table_name)  # Returns state (exists now!)

   # Check if SQL changed
   current_sql_hash = state_manager.compute_sql_hash(new_query)
   if state.sql_hash != current_sql_hash:
       return False  # SQL changed → Full load
   ```

   **Important Note**: In this test, the SQL query changes (we add `value` to SELECT), so the SQL hash will be different IF the state has a saved SQL hash. However, since we're calling `MaterializationHandler` directly (not through `ModelExecutor`), the SQL hash might not be properly saved in Step 1.

   **What actually happens in the test:**
   - If state has `sql_hash == "unknown"` or no SQL hash: `should_run_incremental()` can return `True` for append strategy (it doesn't strictly require SQL hash match for append)
   - If state has a different SQL hash: `should_run_incremental()` returns `False` → Full load

   **In real-world scenarios**:
   - SQL query stays the same: `SELECT * FROM source_events`
   - Source table schema changes (adds a column)
   - Query output schema changes, but SQL hash stays the same
   - Incremental run → Schema change detected → Handled per `on_schema_change`

4. **If `should_run_incremental()` returns `True`** (incremental run):
   - Calls `execute_append_strategy()`
   - **Schema change check happens here (BEFORE incremental execution):**
     ```python
     if adapter.table_exists(table_name):  # True - table exists
         handler = SchemaChangeHandler(adapter)
         comparator = SchemaComparator(adapter)

         query_schema = comparator.infer_query_schema(sql_query)
         # Returns: [{"name": "event_id", "type": "INTEGER"},
         #           {"name": "event_name", "type": "VARCHAR"},
         #           {"name": "event_date", "type": "DATE"},
         #           {"name": "value", "type": "INTEGER"}]  # ← New column!

         table_schema = comparator.get_table_schema(table_name)
         # Returns: [{"name": "event_id", "type": "INTEGER"},
         #           {"name": "event_name", "type": "VARCHAR"},
         #           {"name": "event_date", "type": "DATE"}]  # ← Old schema

         handler.handle_schema_changes(
             table_name,
             query_schema,
             table_schema,
             "append_new_columns",  # ← From metadata["incremental"]["on_schema_change"]
             sql_query=sql_query,
             full_incremental_refresh_config=full_incremental_refresh_config,
             incremental_config=incremental_config,
         )
     ```

5. **SchemaChangeHandler.handle_schema_changes()**:
   - Compares schemas → Detects new column: `value`
   - Calls `_handle_append_new_columns()`
   - Executes: `ALTER TABLE target_events ADD COLUMN value INTEGER`
   - Table now has 4 columns

6. **Continues with incremental execution**:
   - Gets `last_processed_value` from state
   - Applies time filter: `event_date > '2024-01-01'` (or similar)
   - Executes filtered query and appends to table

**If `should_run_incremental()` returns `False`** (full load):
   - Executes: `adapter.create_table(table_name, sql_query, metadata)`
   - This recreates the table with the new schema (4 columns including `value`)
   - **Note**: This is a full load, so schema change handling doesn't run (table is recreated anyway)

**Result**: Table `target_events` now has:
- Schema: `event_id`, `event_name`, `event_date`, `value` (4 columns - new column added!)
- Data: Either:
  - Full load: All rows from new query (if SQL changed)
  - Incremental: Original rows + new incremental rows (if SQL unchanged)

## Key Points

### 1. State Manager's Role

**State Manager determines:**
- **First run** (no state): Full load → Creates table
- **Subsequent runs** (state exists, SQL/config unchanged): Incremental → Appends/merges data
- **After changes** (SQL/config changed): Full load → Recreates table

**In tests:**
- We manually create/update state to simulate "previous run"
- This makes the test run incrementally (not full load)
- This is necessary to trigger schema change detection

### 2. Schema Change Detection Timing

**Schema change detection happens:**
- **Only** when running incrementally (not full load)
- **Only** when table exists
- **Before** incremental execution (so schema is correct before inserting data)

**Why not on full load?**
- Full load recreates the table anyway
- No need to check schema changes (table is being replaced)

### 3. Who Triggers `on_schema_change`?

**Trigger Point**: `IncrementalExecutor` strategy methods (`execute_append_strategy`, `execute_merge_strategy`, `execute_delete_insert_strategy`)

**Flow:**
```
IncrementalExecutor.execute_append_strategy()
  ↓
if adapter.table_exists(table_name):  # Check if table exists
  ↓
SchemaComparator.infer_query_schema(sql_query)  # Get query output schema
SchemaComparator.get_table_schema(table_name)    # Get existing table schema
  ↓
SchemaChangeHandler.handle_schema_changes(
    query_schema, table_schema, on_schema_change, ...
)  # ← THIS IS WHERE on_schema_change IS USED
  ↓
Continue with incremental execution
```

**The `on_schema_change` value comes from:**
- `metadata["incremental"]["on_schema_change"]`
- Extracted in `MaterializationHandler._execute_incremental_materialization()`
- Passed to `IncrementalExecutor` strategy methods
- Used by `SchemaChangeHandler.handle_schema_changes()`

### 4. Test Limitations

**Current test approach:**
- Changes SQL query (adds column to SELECT)
- This changes SQL hash → Would normally trigger full load
- But we want to test incremental with schema change

**Real-world scenario:**
- SQL query stays the same: `SELECT * FROM source_events`
- Source table schema changes (adds column)
- Query output schema changes, but SQL hash stays the same
- Incremental run detects schema change

**To make test more realistic:**
- Could use `SELECT * FROM source_events` in both runs
- Change source table schema between runs
- SQL hash stays same → Incremental run → Schema change detected

## Complete Flow Diagram

```
Test Setup:
├── adapter: DuckDB database connection
├── state_manager: Tracks execution state
├── handler: MaterializationHandler(adapter, state_manager, {})
└── initial_table_with_data: source_events table with 3 rows

Test Execution:
│
├─ Step 1: First Run (Full Load)
│  ├── handler.materialize("target_events", "SELECT id, name, date FROM source", ...)
│  ├── should_run_incremental() → False (no state)
│  ├── adapter.create_table() → Creates table with 3 columns
│  └── state_manager.update_processed_value() → Saves state (last_processed_value)
│
├─ Step 2: Set Up State (Simulate Previous Run)
│  └── state_manager.update_processed_value() → Updates last_processed_value
│      (Preserves existing sql_hash and config_hash)
│
└─ Step 3: Second Run (Incremental with Schema Change)
   ├── handler.materialize("target_events", "SELECT id, name, date, value FROM source", ...)
   ├── should_run_incremental() → True/False (depends on SQL hash)
   │
   ├─ IF should_run_incremental() == True (Incremental):
   │  ├── execute_append_strategy()
   │  ├── if table_exists() → True
   │  ├── SchemaComparator.infer_query_schema() → 4 columns
   │  ├── SchemaComparator.get_table_schema() → 3 columns
   │  ├── SchemaChangeHandler.handle_schema_changes()
   │  │  └── Detects new column → ALTER TABLE ADD COLUMN value
   │  └── Continue with incremental append
   │
   └─ IF should_run_incremental() == False (Full Load):
      └── adapter.create_table() → Recreates table with 4 columns
```

## Summary

### State Manager (`ModelStateManager`)

**Purpose**: Tracks execution state for incremental models

**What it stores**:
- `last_processed_value`: Last processed timestamp for time filtering
- `sql_hash`: Hash of SQL query (to detect query changes)
- `config_hash`: Hash of incremental config (to detect config changes)
- `strategy`: Which incremental strategy was used

**How it's used**:
- `IncrementalExecutor.should_run_incremental()` checks state to decide:
  - No state → Full load
  - State exists + SQL/config unchanged → Incremental
  - State exists + SQL/config changed → Full load

**In tests vs production**:
- **Production**: `ModelExecutor.save_model_state()` saves SQL/config hashes after execution
- **Tests**: We call `MaterializationHandler` directly, so SQL/config hashes might not be saved
- This allows tests to run incrementally even with changed SQL (state has "unknown" hash)

### Who Runs the Model?

**Production Flow**:
```
User/CLI
  ↓
ExecutionEngine.execute_models()
  ↓
ModelExecutor.execute()
  ↓ (calls save_model_state() after execution)
MaterializationHandler.materialize()
  ↓
IncrementalExecutor.execute_append_strategy()
```

**In Tests**:
- Directly call `MaterializationHandler.materialize()`
- Bypass `ModelExecutor` (simpler, but SQL/config hashes might not be saved)

### Who Triggers `on_schema_change`?

**Trigger Point**: `IncrementalExecutor` strategy methods

**Flow**:
```
IncrementalExecutor.execute_append_strategy()
  ↓
if adapter.table_exists(table_name):  # Check if table exists
  ↓
SchemaComparator.infer_query_schema(sql_query)  # Get query output schema
SchemaComparator.get_table_schema(table_name)    # Get existing table schema
  ↓
SchemaChangeHandler.handle_schema_changes(
    query_schema,
    table_schema,
    on_schema_change,  # ← From metadata["incremental"]["on_schema_change"]
    ...
)
  ↓
Continue with incremental execution
```

**Key Points**:
- Happens **before** incremental execution (so schema is correct before inserting data)
- Only when table exists and running incrementally
- `on_schema_change` value comes from `metadata["incremental"]["on_schema_change"]`
- Extracted in `MaterializationHandler._execute_incremental_materialization()`
- Passed to `IncrementalExecutor` strategy methods
- Used by `SchemaChangeHandler.handle_schema_changes()`

### What the Test Verifies

1. **Schema Detection**: Schema changes are detected correctly (new columns, missing columns, type mismatches)
2. **Schema Handling**: Schema changes are handled according to `on_schema_change` setting
3. **Final Schema**: Final table schema matches expectations (columns added/removed correctly)
4. **Data Correctness**: Data is correct after schema changes (values in right columns, no data loss)

### Test Structure

Each test follows this pattern:
1. **Setup**: Create source table with data
2. **Step 1**: First run (full load) - creates table with initial schema
3. **Step 2**: Set up state - ensures next run will be incremental
4. **Step 3**: Second run with schema change - tests `on_schema_change` behavior
5. **Verification**: Check both schema and data correctness
