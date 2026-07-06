# on_schema_change Actions Reference

## Overview

The `on_schema_change` parameter controls how incremental materialization handles schema differences between the transformation output and the existing target table. This document defines all supported actions and their behaviors.

## Supported Actions

### 1. `fail` (Default)

**Behavior:** Fail the transformation if any schema differences are detected.

**What happens:**
- ❌ Transformation stops immediately if schema differences found
- ✅ Raises clear error message describing differences
- ✅ Prevents unexpected data corruption
- ✅ Forces explicit schema change handling

**Use cases:**
- Production environments requiring strict schema control
- When schema changes should be reviewed manually
- When you want to catch schema drift early
- Compliance/audit scenarios
- Default behavior for safety

**Example:**
```python
@model(
    table_name="customers",
    materialization="incremental",
    incremental={
        "strategy": "merge",
        "on_schema_change": "fail"  # or omit for default
    }
)
def customers():
    return "SELECT customer_id, name, email FROM ..."
```

**Error message format:**
```
Schema changes detected for table 'customers' but on_schema_change='fail'.
New columns: ['phone_number', 'address']
Missing columns: ['old_column']
Type mismatches: {'email': ('VARCHAR(100)', 'TEXT')}
```

**Risks:**
- None - fails safely before data corruption
- Requires manual intervention for any schema change

---

### 2. `ignore`

**Behavior:** Ignore schema differences and proceed with the incremental operation.

**What happens:**
- ✅ Transformation executes normally
- ⚠️ New columns in output are ignored (not added to table)
- ⚠️ Missing columns in output remain in table
- ⚠️ Type mismatches may cause errors during INSERT/MERGE
- ⚠️ Column order differences may cause data misalignment

**Use cases:**
- When schema changes are handled manually
- When you want explicit control over schema evolution
- Legacy systems where schema changes are managed externally

**Example:**
```python
@model(
    table_name="orders",
    materialization="incremental",
    incremental={
        "strategy": "append",
        "on_schema_change": "ignore"
    }
)
def orders():
    return "SELECT order_id, customer_id, total FROM ..."
```

**Risks:**
- Data may be inserted into wrong columns if order changes
- Type mismatches will cause runtime errors
- New columns won't be available in target table

---

### 3. `append_new_columns`

**Behavior:** Automatically add new columns from transformation output to target table. Existing columns remain unchanged.

**What happens:**
- ✅ New columns in output are automatically added to table
- ✅ Existing columns remain in table (even if missing from output)
- ✅ Missing columns in output are NOT removed from table
- ⚠️ Type mismatches may still cause errors
- ⚠️ Column order differences may cause data misalignment

**Use cases:**
- When you frequently add new columns
- When you want to preserve existing columns
- When column removal should be manual
- Most common production use case

**Example:**
```python
@model(
    table_name="orders",
    materialization="incremental",
    incremental={
        "strategy": "append",
        "on_schema_change": "append_new_columns",
        "append": {
            "filter_column": "created_at"
        }
    }
)
def orders():
    # If this query adds 'discount_code' column, it will be auto-added to table
    return "SELECT order_id, customer_id, total, discount_code FROM ..."
```

**DDL generated:**
```sql
ALTER TABLE orders ADD COLUMN discount_code VARCHAR(50);
```

**Risks:**
- Type mismatches on existing columns still cause errors
- Orphaned columns (in table but not in output) accumulate over time
- Column order issues if not handled properly

---

### 4. `sync_all_columns`

**Behavior:** Synchronize target table schema with transformation output by adding new columns and removing missing columns.

**What happens:**
- ✅ New columns in output are automatically added to table
- ✅ Missing columns in output are automatically removed from table
- ⚠️ Type changes may require manual intervention (database-dependent)
- ⚠️ Data loss risk when columns are removed
- ⚠️ Column order differences may cause data misalignment

**Use cases:**
- When transformation output is the source of truth
- When you want exact schema matching
- Development/testing environments
- When column removal is intentional

**Example:**
```python
@model(
    table_name="products",
    materialization="incremental",
    incremental={
        "strategy": "merge",
        "on_schema_change": "sync_all_columns",
        "merge": {
            "unique_key": ["product_id"],
            "filter_column": "updated_at"
        }
    }
)
def products():
    # If 'old_column' was removed from query, it will be dropped from table
    return "SELECT product_id, name, price, new_column FROM ..."
```

**DDL generated:**
```sql
ALTER TABLE products ADD COLUMN new_column VARCHAR(100);
ALTER TABLE products DROP COLUMN old_column;  -- With warning
```

**Warnings:**
- Logs warning before dropping columns
- May require database-specific permissions
- Some databases don't support DROP COLUMN

**Risks:**
- **Data loss** when columns are removed
- May break downstream dependencies
- Type changes may fail (database-dependent)

---

### 5. `full_refresh`

**Behavior:** Drop the existing table and recreate it with the full transformation output (no incremental filtering).

**What happens:**
- ✅ Existing table is dropped
- ✅ Table is recreated with full transformation output
- ✅ All data is refreshed (no incremental filtering applied)
- ⚠️ All existing data is lost and replaced

**Use cases:**
- When you need a complete refresh of the table
- After major schema changes
- When incremental logic is not needed for this run

**Example:**
```python
@model(
    table_name="products",
    materialization="incremental",
    incremental={
        "strategy": "append",
        "filter_condition": "updated_at >= '@start_date'",
        "on_schema_change": "full_refresh"
    }
)
def products():
    return "SELECT product_id, name, price, category FROM ..."
```

**DDL generated:**
```sql
DROP TABLE products;
CREATE TABLE products AS SELECT product_id, name, price, category FROM ...;
```

**Risks:**
- **All existing data is lost** and replaced
- No incremental filtering - processes all data
- May take longer for large tables

---

### 6. `full_incremental_refresh`

**Behavior:** Drop the existing table, recreate it, then immediately run the incremental strategy in chunks until reaching the end condition.

**What happens:**
- ✅ Existing table is dropped
- ✅ Table is recreated (empty or with initial data)
- ✅ Incremental strategy runs in chunks:
  - Starts with `start_value` for each parameter
  - Increments by `step` until reaching `end_value`
  - `end_value` expressions are evaluated against **source table(s)**
  - Executes incremental strategy for each chunk
- ✅ Continues until all parameters reach their `end_value`

**Use cases:**
- When schema changes require full backfill
- When you need to rebuild table with incremental chunking
- Large datasets that need to be processed in manageable chunks

**Example:**
```python
@model(
    table_name="events",
    materialization="incremental",
    incremental={
        "strategy": "append",
        "filter_condition": "event_date >= '@start_date'",
        "on_schema_change": "full_incremental_refresh"
    }
)

full_incremental_refresh:
  parameters:
    - name: "@start_date"
      start_value: "2024-01-01"
      end_value: "max(event_date)"  # Evaluated against source table
      step: "INTERVAL 1 DAY"
```

**Execution flow:**
1. Drop table `events`
2. Recreate table `events` (empty)
3. Run incremental chunks:
   - Chunk 1: `@start_date='2024-01-01'` → process data
   - Chunk 2: `@start_date='2024-01-02'` → process data
   - ... continue until `max(event_date)` is reached

**Risks:**
- All existing data is lost initially
- Requires careful configuration of parameters
- `end_value` expressions must be valid SQL against source tables
- May take significant time for large date ranges

---

### 7. `recreate_empty`

**Behavior:** Drop the existing table and recreate it as an empty table (no data).

**What happens:**
- ✅ Existing table is dropped
- ✅ Table is recreated with correct schema (empty, no data)
- ✅ No data is loaded by t4t
- ✅ Backfilling is expected to be done by external tool

**Use cases:**
- When backfilling is done using a different tool
- When you want t4t to only manage schema, not data
- Integration with external ETL processes

**Example:**
```python
@model(
    table_name="staging_data",
    materialization="incremental",
    incremental={
        "strategy": "append",
        "filter_condition": "created_at >= '@start_date'",
        "on_schema_change": "recreate_empty"
    }
)
def staging_data():
    return "SELECT id, name, value FROM ..."
```

**DDL generated:**
```sql
DROP TABLE staging_data;
CREATE TABLE staging_data (id INTEGER, name VARCHAR, value DECIMAL);
-- No INSERT statements - table remains empty
```

**Risks:**
- Table will be empty after recreation
- Requires external process to populate data
- May break downstream dependencies if they expect data

---

## Action Comparison Matrix

| Action | Add New Columns | Remove Missing Columns | Handle Type Changes | Fail on Differences | Data Loss Risk |
|--------|----------------|------------------------|---------------------|---------------------|----------------|
| `fail` (default) | ❌ No | ❌ No | ❌ No | ✅ Yes | ✅ None |
| `ignore` | ❌ No | ❌ No | ❌ No | ❌ No | ⚠️ Medium (misalignment) |
| `append_new_columns` | ✅ Yes | ❌ No | ❌ No | ❌ No | ⚠️ Low |
| `sync_all_columns` | ✅ Yes | ✅ Yes | ⚠️ Partial | ❌ No | ⚠️ High (if columns removed) |
| `full_refresh` | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No | ⚠️ High (all data replaced) |
| `full_incremental_refresh` | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No | ⚠️ High (all data replaced, then backfilled) |
| `recreate_empty` | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No | ⚠️ High (all data lost, empty table) |

## Schema Change Types

Each action handles these schema change scenarios differently:

### 1. New Columns Added
- **Query has:** `order_id, customer_id, discount_code`
- **Table has:** `order_id, customer_id`
- **Difference:** `discount_code` is new

| Action | Result |
|--------|--------|
| `fail` | Transformation fails |
| `ignore` | Column ignored, INSERT may fail |
| `append_new_columns` | ✅ `discount_code` added to table |
| `sync_all_columns` | ✅ `discount_code` added to table |
| `full_refresh` | ✅ Table recreated, `discount_code` included |
| `full_incremental_refresh` | ✅ Table recreated, then backfilled with `discount_code` |
| `recreate_empty` | ✅ Table recreated with `discount_code` (empty) |

### 2. Columns Removed
- **Query has:** `order_id, customer_id`
- **Table has:** `order_id, customer_id, old_column`
- **Difference:** `old_column` is missing from query

| Action | Result |
|--------|--------|
| `fail` | Transformation fails |
| `ignore` | Column remains, INSERT may fail |
| `append_new_columns` | Column remains (not removed) |
| `sync_all_columns` | ⚠️ `old_column` dropped from table (with warning) |
| `full_refresh` | ✅ Table recreated, `old_column` not included |
| `full_incremental_refresh` | ✅ Table recreated, then backfilled without `old_column` |
| `recreate_empty` | ✅ Table recreated without `old_column` (empty) |

### 3. Type Mismatches
- **Query has:** `email VARCHAR(255)`
- **Table has:** `email TEXT`
- **Difference:** Same column, different type

| Action | Result |
|--------|--------|
| `fail` | Transformation fails |
| `ignore` | May cause INSERT/MERGE errors |
| `append_new_columns` | May cause INSERT/MERGE errors |
| `sync_all_columns` | ⚠️ May attempt type change (database-dependent) |
| `full_refresh` | ✅ Table recreated with new type |
| `full_incremental_refresh` | ✅ Table recreated with new type, then backfilled |
| `recreate_empty` | ✅ Table recreated with new type (empty) |

### 4. Column Order Changes
- **Query has:** `order_id, customer_id, total`
- **Table has:** `order_id, total, customer_id`
- **Difference:** Same columns, different order

| Action | Result |
|--------|--------|
| `fail` | Transformation fails |
| `ignore` | ⚠️ Data may be inserted into wrong columns |
| `append_new_columns` | ⚠️ Data may be inserted into wrong columns |
| `sync_all_columns` | ⚠️ Data may be inserted into wrong columns |
| `full_refresh` | ✅ Table recreated with correct column order |
| `full_incremental_refresh` | ✅ Table recreated with correct order, then backfilled |
| `recreate_empty` | ✅ Table recreated with correct order (empty) |

## Recommended Practices

### Production Environments
- **Recommended:** `append_new_columns` or `fail`
- **Avoid:** `sync_all_columns` (data loss risk)
- **Rationale:** Safe schema evolution with explicit control

### Development/Testing
- **Recommended:** `sync_all_columns` or `append_new_columns`
- **Rationale:** Faster iteration, schema matches code

### Critical Data
- **Recommended:** `fail`
- **Rationale:** Explicit review of all schema changes

### Frequent Schema Evolution
- **Recommended:** `append_new_columns`
- **Rationale:** Automatic handling of new columns, preserves existing

## Database Compatibility

| Database | ADD COLUMN | DROP COLUMN | Type Change | Notes |
|----------|------------|-------------|-------------|-------|
| Snowflake | ✅ Yes | ✅ Yes | ✅ Yes | Full support |
| PostgreSQL | ✅ Yes | ✅ Yes | ⚠️ Limited | Some type changes require explicit casting |
| BigQuery | ✅ Yes | ⚠️ Limited | ❌ No | DROP COLUMN has restrictions |
| DuckDB | ✅ Yes | ✅ Yes | ✅ Yes | Full support |
| MySQL | ✅ Yes | ✅ Yes | ⚠️ Limited | Type changes may require ALTER |
| SQL Server | ✅ Yes | ✅ Yes | ⚠️ Limited | Type changes may require explicit conversion |

## Future Enhancements (Not in Initial Implementation)

These actions may be considered for future versions:

1. **`warn`**: Log warnings but proceed (similar to `ignore` but with visibility)
2. **`append_new_columns_safe`**: Add new columns with type checking
3. **`sync_with_backup`**: Sync columns but backup dropped column data first
4. **`migrate_types`**: Explicitly handle type changes with conversion logic
5. **`rename_columns`**: Support column renaming/mapping

## Implementation Notes

- Default value should be `"fail"` for safety (per OTS 0.2.1)
- All actions should log what they're doing at INFO level
- `sync_all_columns` should require explicit confirmation or flag for production
- Type changes may need separate configuration or manual handling
- Column order handling may require explicit column mapping in INSERT statements
