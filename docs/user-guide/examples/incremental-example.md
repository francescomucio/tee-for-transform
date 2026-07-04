# Incremental Materialization Example

This example demonstrates how to use t4t's incremental materialization feature to efficiently process large datasets.

## Project Structure

```
t_project/
├── models/
│   └── my_schema/
│       ├── incremental_example.sql
│       └── incremental_example.py
├── data/
│   ├── t_project.duckdb
│   └── tee_state.db
└── project.toml
```

## Configuration

### Project Configuration (`project.toml`)

```toml
project_folder = "t_project"

[connection]
type = "duckdb"
path = "t_project/data/t_project.duckdb"
schema = "my_schema"

[flags]
materialization_change_behavior = "warn"
```

### Model Configuration (`incremental_example.py`)

```python
from t4t.typing import ModelMetadata

# Example 1: Append strategy
metadata_append: ModelMetadata = {
    "description": "Incremental table using append strategy",
    "materialization": "incremental",
    "incremental": {
        "strategy": "append",
        "append": {
            "filter_column": "created_at",
            "start_value": "2024-01-01",
            "lookback": "7 days"
        }
    }
}

# Example 2: Merge strategy
metadata_merge: ModelMetadata = {
    "description": "Incremental table using merge strategy",
    "materialization": "incremental",
    "incremental": {
        "strategy": "merge",
        "merge": {
            "unique_key": ["id"],
            "filter_column": "updated_at",
            "start_value": "auto",
            "lookback": "3 hours"
        }
    }
}

# Example 3: Delete+Insert strategy
metadata_delete_insert: ModelMetadata = {
    "description": "Incremental table using delete+insert strategy",
    "materialization": "incremental",
    "incremental": {
        "strategy": "delete_insert",
        "delete_insert": {
            "where_condition": "updated_at >= @start_date",
            "filter_column": "updated_at",
            "start_value": "@start_date"
        }
    }
}

# Choose which strategy to use
metadata = metadata_merge  # Currently using merge strategy
```

### SQL Model (`incremental_example.sql`)

```sql
-- Incremental example model
-- This demonstrates how to use incremental materialization

SELECT 
    id,
    name,
    created_at,
    updated_at,
    status
FROM t_project.source_table
WHERE status = 'active'
```

## Running the Example

### First Run (Full Load)

```bash
uv run t4t run ./t_project
```

**Output:**
```
INFO - ExecutionEngine - Executing model: my_schema.incremental_example
INFO - DuckDBAdapter - Created table: my_schema.incremental_example
INFO - ExecutionEngine - Successfully executed my_schema.incremental_example with 256 rows
```

### Subsequent Runs (Incremental)

```bash
uv run t4t run ./t_project
```

**Output:**
```
INFO - ExecutionEngine - Executing model: my_schema.incremental_example
INFO - t4t.engine.incremental_executor - Running incremental merge for my_schema.incremental_example with auto start_value
INFO - DuckDBAdapter - Executed incremental merge
INFO - ExecutionEngine - Successfully executed my_schema.incremental_example with 256 rows
```

### Using CLI Variables

```bash
uv run t4t run ./t_project --vars '{"start_date": "2024-01-01"}'
```

**Output:**
```
INFO - ExecutionEngine - Executing model: my_schema.incremental_example
INFO - t4t.engine.incremental_executor - Running incremental delete_insert for my_schema.incremental_example with @start_date start_value
INFO - t4t.engine.incremental_executor - Resolved variable @start_date to 2024-01-01
INFO - DuckDBAdapter - Executed delete for table: my_schema.incremental_example
INFO - DuckDBAdapter - Executed insert for table: my_schema.incremental_example
INFO - ExecutionEngine - Successfully executed my_schema.incremental_example with 256 rows
```

## Generated SQL Examples

### Append Strategy

**First Run:**
```sql
CREATE TABLE my_schema.incremental_example AS
SELECT id, name, created_at, updated_at, status
FROM t_project.source_table
WHERE status = 'active'
AND created_at >= '2024-01-01'
```

**Subsequent Runs:**
```sql
INSERT INTO my_schema.incremental_example
SELECT id, name, created_at, updated_at, status
FROM t_project.source_table
WHERE status = 'active'
AND created_at > '2024-01-15'  -- Last processed timestamp
```

### Merge Strategy

**First Run:**
```sql
CREATE TABLE my_schema.incremental_example AS
SELECT id, name, created_at, updated_at, status
FROM t_project.source_table
WHERE status = 'active'
```

**Subsequent Runs:**
```sql
MERGE INTO my_schema.incremental_example AS target
USING (
    SELECT id, name, created_at, updated_at, status
    FROM t_project.source_table
    WHERE status = 'active'
    AND updated_at > (SELECT COALESCE(MAX(updated_at) - INTERVAL '3 hours', '1900-01-01') FROM my_schema.incremental_example)
) AS source
ON target.id = source.id
WHEN MATCHED THEN UPDATE SET 
    name = source.name,
    created_at = source.created_at,
    updated_at = source.updated_at,
    status = source.status
WHEN NOT MATCHED THEN INSERT (id, name, created_at, updated_at, status)
VALUES (source.id, source.name, source.created_at, source.updated_at, source.status)
```

### Delete+Insert Strategy

**First Run:**
```sql
CREATE TABLE my_schema.incremental_example AS
SELECT id, name, created_at, updated_at, status
FROM t_project.source_table
WHERE status = 'active'
```

**Subsequent Runs:**
```sql
DELETE FROM my_schema.incremental_example
WHERE updated_at >= CAST('2024-01-01' AS DATE)

INSERT INTO my_schema.incremental_example
SELECT id, name, created_at, updated_at, status
FROM t_project.source_table
WHERE status = 'active'
AND updated_at >= '2024-01-01'
```

## State Management

t4t automatically tracks the state of incremental models in `t_project/data/tee_state.db`:

```sql
-- Check model state
SELECT * FROM tee_model_state WHERE model_name = 'my_schema.incremental_example';

-- Example output:
-- model_name: my_schema.incremental_example
-- materialization: incremental
-- last_execution_timestamp: 2024-01-15T10:30:00
-- sql_hash: 90a73e6c9b2609ee79037c3ab2a6aaf8da77e64653024f7bb6261351fb59c688
-- config_hash: 080cb98279c3da70f2ff185c3b36f87b18607575b1ede501a403c7e9066f6d81
-- last_processed_value: 2024-01-15T10:30:00
-- strategy: merge
```

## Testing Different Strategies

### Switch to Append Strategy

```python
# In incremental_example.py
metadata = metadata_append  # Switch to append strategy
```

### Switch to Delete+Insert Strategy

```python
# In incremental_example.py
metadata = metadata_delete_insert  # Switch to delete+insert strategy
```

### Test with Different Variables

```bash
# Test with different start dates
uv run t4t run ./t_project --vars '{"start_date": "2024-02-01"}'

# Test with different time ranges
uv run t4t run ./t_project --vars '{"start_date": "2024-01-15"}'
```

## Monitoring and Debugging

### Enable Debug Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Check Execution Logs

```bash
uv run t4t run ./t_project 2>&1 | grep -i "incremental\|merge\|append\|delete"
```

### Verify State

```bash
# Check if state database exists
ls -la t_project/data/tee_state.db

# Query state (requires DuckDB CLI)
duckdb t_project/data/tee_state.db "SELECT * FROM tee_model_state;"
```

## Best Practices

1. **Choose the Right Strategy**:
   - Use `append` for append-only data (logs, events)
   - Use `merge` for slowly changing dimensions
   - Use `delete+insert` for time-partitioned data

2. **Optimize Time Columns**:
   - Use indexed columns for time filtering
   - Consider partitioning large tables

3. **Handle Late-Arriving Data**:
   - Use appropriate lookback periods
   - Monitor for data quality issues

4. **Test Thoroughly**:
   - Test with different data scenarios
   - Verify incremental runs produce correct results
   - Test edge cases (empty tables, missing data)

## Troubleshooting

### Common Issues

1. **Model always runs full load**:
   - Check that the model has been run at least once
   - Verify state database exists and is accessible

2. **Variable resolution not working**:
   - Ensure variables are passed via `--vars` flag
   - Check variable name spelling and syntax

3. **Date casting errors**:
   - Ensure date values are in correct format (YYYY-MM-DD)
   - Check that time columns have appropriate data types

For more detailed information, see the [Incremental Materialization Guide](../incremental-materialization.md).
