# Incremental Materialization

t4t supports incremental materialization for efficient data processing, allowing you to process only new or changed data instead of reprocessing entire datasets. This is particularly useful for large datasets where full refreshes are expensive.

## Overview

Incremental materialization in t4t supports three main strategies:

- **Append**: Add new records to existing tables
- **Merge**: Update existing records and insert new ones (upsert)
- **Delete+Insert**: Remove old data and insert fresh data for a specific time range

## Configuration

Incremental materialization is configured through model metadata. You can define this in either:

1. **Python metadata files** (`.py`) - Recommended for complex configurations
2. **SQL comment metadata** - For simple configurations

### Python Metadata Configuration

```python
# models/my_schema/incremental_example.py
from t4t.typing import ModelMetadata

# Append strategy
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

# Merge strategy
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

# Delete+Insert strategy
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

### SQL Comment Configuration

```sql
-- models/my_schema/incremental_example.sql
-- metadata: {"materialization": "incremental", "incremental": {"strategy": "append", "append": {"filter_column": "created_at", "start_value": "2024-01-01", "lookback": "7 days"}}}

SELECT id, name, created_at, updated_at, status
FROM t_project.source_table
WHERE status = 'active'
```

## AutoIncremental Columns

For dimension tables and similar use cases where you need to calculate stable IDs based on existing data in the target table, t4t supports **auto_incremental columns**. When a column is marked as `auto_incremental: True`, the system automatically handles ID calculation logic using `MAX(id) + ROW_NUMBER()`.

### Benefits

- **Stable IDs**: IDs remain consistent across incremental loads
- **Automatic Handling**: System handles MAX(id) calculation, exclusion of existing records, and ID assignment
- **Works with All Strategies**: Supports merge, append, and delete+insert strategies
- **Transparent and Explicit**: Recommended explicit mode makes ID calculation visible in your query

### Configuration

Mark a column as auto_incremental in your schema metadata:

```python
metadata: ModelMetadata = {
    "description": "Brand dimension table",
    "materialization": "incremental",
    "incremental": {
        "strategy": "merge",
        "merge": {
            "unique_key": ["brand_name"],  # Required for merge strategy
            "filter_column": "created_date",
            "start_value": "auto",
        }
    },
    "schema": [
        {
            "name": "brand_id",
            "datatype": "integer",
            "auto_incremental": True,  # System will calculate IDs automatically
        },
        {
            "name": "brand_name",
            "datatype": "string",
        }
    ]
}
```

## Explicit Mode (Recommended) ⭐

**Explicit mode is the recommended approach** because it makes ID calculation transparent and gives you full control over how IDs are assigned. In explicit mode, you include the ID column in your query using `ROW_NUMBER()` or any other expression.

### How Explicit Mode Works

**User Query (Explicit - Includes ID Column):**
```sql
SELECT
    row_number() over (order by brand) as brand_id,
    brand as brand_name
FROM source_table
WHERE brand IS NOT NULL
GROUP BY brand
```

**For Full Refresh:**
- Query executes as-is
- IDs will be 1, 2, 3, ... (sequential)

**For Incremental Runs:**
- System automatically modifies the `ROW_NUMBER()` expression
- Changes: `row_number() over (order by brand)` → `(MAX(id) + row_number() over (order by brand))`
- Only new records (not in target table) get calculated IDs
- Existing records maintain their original IDs

**Example Transformation:**
```sql
-- Original query (full refresh)
SELECT
    row_number() over (order by brand) as brand_id,
    brand as brand_name
FROM source_table
WHERE brand IS NOT NULL
GROUP BY brand

-- Incremental run (system automatically modifies)
WITH source_data AS (
    SELECT
        row_number() over (order by brand) as brand_id,
        brand as brand_name
    FROM source_table
    WHERE brand IS NOT NULL
    GROUP BY brand
),
existing_data AS (
    SELECT brand_name FROM dim_brand
),
max_id AS (
    SELECT COALESCE(MAX(brand_id), 0) AS max_id FROM dim_brand
)
SELECT DISTINCT
    (m.max_id + s.brand_id) AS brand_id,  -- MAX(id) added to existing expression
    s.brand_name
FROM source_data s
CROSS JOIN max_id m
LEFT JOIN existing_data e ON s.brand_name = e.brand_name
WHERE e.brand_name IS NULL  -- Only new records
```

### Why Explicit Mode is Better

1. **Transparency**: You can see exactly how IDs are calculated in your query
2. **Flexibility**: You can use any expression (not just `ROW_NUMBER()`)
3. **Debugging**: Easier to understand and debug when IDs are visible
4. **Control**: Full control over ID calculation logic (ordering, partitioning, etc.)
5. **Standard SQL**: Uses standard SQL patterns (`ROW_NUMBER()`, `GROUP BY`)

## Implicit Mode (Alternative)

Implicit mode is an alternative where you write a simple query without the ID column, and the system fully wraps it with ID calculation logic.

### How Implicit Mode Works

**User Query (Simple - No ID Column):**
```sql
SELECT DISTINCT brand AS brand_name
FROM source_table
WHERE brand IS NOT NULL
```

**System Automatically Wraps With:**
```sql
WITH source_data AS (
    SELECT DISTINCT brand AS brand_name
    FROM source_table
    WHERE brand IS NOT NULL
      AND created_date > 'last_value'  -- Time filter if filter_column specified
),
existing_data AS (
    SELECT brand_name FROM dim_brand
),
max_id AS (
    SELECT COALESCE(MAX(brand_id), 0) AS max_id
    FROM dim_brand
)
SELECT DISTINCT
    m.max_id + ROW_NUMBER() OVER (ORDER BY s.brand_name) AS brand_id,
    s.brand_name
FROM source_data s
CROSS JOIN max_id m
LEFT JOIN existing_data e ON s.brand_name = e.brand_name
WHERE e.brand_name IS NULL  -- Only new records
```

### When to Use Implicit Mode

- Quick prototyping or simple use cases
- When you prefer the system to handle all ID logic
- Legacy code that already uses simple queries

### Strategy-Specific Behavior

#### Merge Strategy
- Uses `unique_key` to exclude existing records via LEFT JOIN
- Only new records (not matched on `unique_key`) get calculated IDs
- Existing records are updated via MERGE statement

#### Append Strategy
- No exclusion logic needed - just calculates IDs based on MAX(id)
- New records are appended with sequential IDs
- Simpler than merge - no `unique_key` required

#### Delete+Insert Strategy
- Optional `unique_key` for exclusion (if provided)
- If `unique_key` not provided, all records get new IDs
- DELETE removes old records, INSERT adds new with calculated IDs

### Example: Dimension Table Generation (Explicit Mode - Recommended)

```python
# generate_dimension_tables.py
from t4t.parser.processing import create_model

dimensions = ["brand", "category"]
source_table = "my_schema.national_articles"

for dimension in dimensions:
    # Explicit mode: query includes the ID column
    # For full refresh: query executes as-is (IDs will be 1, 2, 3, ...)
    # For incremental: system automatically adds MAX(id) to ROW_NUMBER() expression
    sql = f"""
        SELECT
            row_number() over (order by {dimension}) as {dimension}_id,
            {dimension} as {dimension}_name
        FROM {source_table}
        WHERE {dimension} IS NOT NULL
        GROUP BY {dimension}
    """

    metadata = {
        "description": f"{dimension.capitalize()} dimension table",
        "materialization": "incremental",
        "incremental": {
            "strategy": "merge",
            "merge": {
                "unique_key": [f"{dimension}_name"],
                "filter_column": "created_date",
                "start_value": "auto",
            }
        },
        "schema": [
            {
                "name": f"{dimension}_id",
                "datatype": "integer",
                "auto_incremental": True,  # System handles ID calculation!
            },
            {
                "name": f"{dimension}_name",
                "datatype": "string",
            }
        ]
    }

    create_model(
        table_name=f"dim_{dimension}",
        sql=sql,
        **metadata
    )
```

**Note**: This example uses explicit mode (recommended). The query includes `row_number() over (order by {dimension}) as {dimension}_id`, making the ID calculation transparent. For incremental runs, the system automatically modifies this to `(MAX(id) + row_number() over (order by {dimension}))`.

### Limitations

- **Only one auto_incremental column per table**: Multiple auto_incremental columns are not supported
- **Merge strategy requires unique_key**: When using merge strategy with auto_incremental, `unique_key` must be specified
- **First run handling**: On first run (empty table), `COALESCE(MAX(id), 0)` ensures IDs start at 1
- **Explicit mode expression**: In explicit mode, the system modifies the existing ID expression. Any expression that produces the auto_incremental column will work (not just `ROW_NUMBER()`)

## Strategies

### 1. Append Strategy

The append strategy adds new records to existing tables without modifying existing data.

**Configuration:**
```python
"incremental": {
    "strategy": "append",
    "append": {
        "filter_column": "created_at",           # Column to use for time filtering (source table)
        "destination_filter_column": "created_dt", # Optional: Column name in target table (if different)
        "start_value": "2024-01-01",              # Start value for first run (or "auto")
        "lookback": "7 days"                      # Optional: lookback period
    }
}
```

**Behavior:**
- First run: Creates table with all data matching the time filter
- Subsequent runs: Appends new data based on time filtering
- No modification of existing records

**Example SQL Generated:**
```sql
-- First run
CREATE TABLE my_schema.incremental_example AS
SELECT id, name, created_at, updated_at, status
FROM t_project.source_table
WHERE status = 'active'
AND created_at >= '2024-01-01'

-- Subsequent runs
INSERT INTO my_schema.incremental_example
SELECT id, name, created_at, updated_at, status
FROM t_project.source_table
WHERE status = 'active'
AND created_at > '2024-01-15'  -- Last processed timestamp
```

### 2. Merge Strategy

The merge strategy performs upsert operations, updating existing records and inserting new ones.

**Configuration:**
```python
"incremental": {
    "strategy": "merge",
    "merge": {
        "unique_key": ["id"],                    # Columns that uniquely identify records
        "filter_column": "updated_at",          # Column to use for time filtering (source table)
        "destination_filter_column": "updated_dt", # Optional: Column name in target table (if different)
        "start_value": "auto",                  # Use max(destination_filter_column) from target table
        "lookback": "3 hours"                   # Optional: lookback period
    }
}
```

**Behavior:**
- First run: Creates table with all data
- Subsequent runs: Updates existing records and inserts new ones
- Uses database-specific MERGE/UPSERT syntax

**Example SQL Generated:**
```sql
-- First run
CREATE TABLE my_schema.incremental_example AS
SELECT id, name, created_at, updated_at, status
FROM t_project.source_table
WHERE status = 'active'

-- Subsequent runs
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

### 3. Delete+Insert Strategy

The delete+insert strategy removes old data and inserts fresh data for a specific time range.

**Configuration:**
```python
"incremental": {
    "strategy": "delete_insert",
    "delete_insert": {
        "where_condition": "updated_at >= @start_date",  # Condition for deletion
        "filter_column": "updated_at",                  # Column for time filtering (source table)
        "destination_filter_column": "updated_dt",      # Optional: Column name in target table (if different)
        "start_value": "@start_date"                    # Variable reference or literal value
    }
}
```

**Behavior:**
- First run: Creates table with all data
- Subsequent runs: Deletes data matching the where condition, then inserts fresh data
- Useful for time-partitioned data or when you need to reprocess specific time ranges

**Example SQL Generated:**
```sql
-- First run
CREATE TABLE my_schema.incremental_example AS
SELECT id, name, created_at, updated_at, status
FROM t_project.source_table
WHERE status = 'active'

-- Subsequent runs
DELETE FROM my_schema.incremental_example
WHERE updated_at >= CAST('2024-01-01' AS DATE)

INSERT INTO my_schema.incremental_example
SELECT id, name, created_at, updated_at, status
FROM t_project.source_table
WHERE status = 'active'
AND updated_at >= '2024-01-01'
```

## Configuration Options

### Filter Column

The `filter_column` specifies which column to use for time-based filtering:

```python
"filter_column": "created_at"    # Use created_at column
"filter_column": "updated_at"    # Use updated_at column
```

### Destination Filter Column

The `destination_filter_column` option allows you to specify a different column name in the target table for the `MAX()` subquery when using `start_value="auto"`. This is useful when the source and target tables have different column names.

```python
"filter_column": "created_date",              # Column in source table
"destination_filter_column": "created_dt",    # Column in target table (if different)
"start_value": "auto"                         # Will query MAX(created_dt) from target
```

**Behavior:**
- If `destination_filter_column` is provided, it's used in the `MAX()` subquery: `MAX(destination_filter_column)`
- If `destination_filter_column` is missing, `filter_column` is used: `MAX(filter_column)`
- The system validates that `destination_filter_column` exists in the target table (raises error if not found)

**Example Use Case:**
```python
# Source table has "created_date", target table has "created_dt"
"incremental": {
    "strategy": "merge",
    "merge": {
        "unique_key": ["brand_name"],
        "filter_column": "created_date",           # Source column
        "destination_filter_column": "created_dt", # Target column
        "start_value": "auto"                      # Queries MAX(created_dt) from target
    }
}
```

**Generated SQL:**
```sql
WHERE created_date > (SELECT MAX(created_dt) FROM my_schema.dim_brand)
```

### Start Value

The `start_value` option controls when to start processing data:

```python
"start_value": "2024-01-01"           # Specific date
"start_value": "auto"                 # Use max(filter_column) from target table
"start_value": "CURRENT_DATE"         # Use current date
"start_value": "@start_date"          # Use CLI variable
"start_value": "{{ start_date }}"     # Use CLI variable (alternative syntax)
```

### Lookback

The `lookback` option adds a buffer period to handle late-arriving data:

```python
"lookback": "7 days"          # 7 days
"lookback": "3 hours"         # 3 hours
"lookback": "30 minutes"      # 30 minutes
"lookback": "2 weeks"         # 2 weeks
"lookback": "1 month"         # 1 month (approximate)
```

**Important:** `lookback` is intended for **date/timestamp-like** `filter_column`s (columns where subtracting an `INTERVAL` is valid in your SQL dialect).
If your `start_value` is not a date/timestamp and your dialect cannot apply `- INTERVAL ...`, you should not use `lookback`.

### CLI Variables

You can pass variables via the command line:

```bash
# Using @variable syntax (JSON format)
uv run t4t run ./examples/t_project --vars '{"start_date": "2024-01-01"}'

# Using {{ variable }} syntax (JSON format)
uv run t4t run ./examples/t_project --vars '{"start_date": "2024-01-01"}'
```

Variables are resolved in the configuration:

```python
"start_value": "@start_date"          # Resolved to 2024-01-01
"where_condition": "created_at >= @start_date"  # Resolved to "created_at >= 2024-01-01"
```

## State Management

t4t automatically tracks the state of incremental models:

- **Execution timestamps**: When the model was last run
- **SQL hashes**: Detects changes in model SQL
- **Config hashes**: Detects changes in model configuration
- **Last processed values**: For tracking incremental progress

State is stored in `examples/t_project/data/t4t_state.db` by default.

## Database Support

### Currently Supported

- **DuckDB**: Full support for all strategies
- **Snowflake**: Planned support (merge strategy ready)

### Database-Specific Features

#### DuckDB
- Native MERGE syntax for merge strategy
- Automatic column detection for merge operations
- Full SQL interval support for lookback periods

#### Snowflake (Planned)
- MERGE syntax with Snowflake-specific optimizations
- Automatic clustering key detection
- Support for Snowflake-specific data types

## Best Practices

### 1. Choose the Right Strategy

- **Append**: Use for append-only data (logs, events, metrics)
- **Merge**: Use for slowly changing dimensions or fact tables
- **Delete+Insert**: Use for time-partitioned data or when you need to reprocess specific ranges

### 2. Optimize Time Columns

- Use indexed columns for time filtering
- Consider partitioning large tables by time columns
- Use appropriate data types (TIMESTAMP, DATE)

### 3. Handle Late-Arriving Data

- Use lookback periods to catch late-arriving data
- Consider the trade-off between lookback period and performance
- Monitor for data quality issues

### 4. Monitor Performance

- Check execution logs for performance issues
- Consider parallel processing for large datasets
- Monitor database resource usage

### 5. Test Incremental Logic

- Test with different data scenarios
- Verify that incremental runs produce correct results
- Test edge cases (empty tables, missing data, etc.)

## Troubleshooting

### Common Issues

1. **Model always runs full load**
   - Check that the model has been run at least once
   - Verify that the state database exists and is accessible
   - Check for configuration changes that trigger full loads

2. **Variable resolution not working**
   - Ensure variables are passed via `--vars` flag
   - Check variable name spelling and syntax
   - Verify that the variable is used in the correct context

3. **Date casting errors**
   - Ensure date values are in correct format (YYYY-MM-DD)
   - Check that time columns have appropriate data types
   - Verify that date comparisons are valid

4. **Merge strategy not working**
   - Check that unique_key columns exist in both source and target
   - Verify that the target table has the expected structure
   - Ensure that the database supports MERGE syntax

### Debug Logging

Enable debug logging to see detailed information:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

This will show:
- Generated SQL queries
- Variable resolution
- State management operations
- Database-specific operations

## Examples

### Complete Example

```python
# models/my_schema/user_events.py
from t4t.typing import ModelMetadata

metadata: ModelMetadata = {
    "description": "Incremental user events table",
    "materialization": "incremental",
    "incremental": {
        "strategy": "merge",
        "merge": {
            "unique_key": ["user_id", "event_id"],
            "filter_column": "event_timestamp",
            "start_value": "auto",
            "lookback": "1 hour"
        }
    }
}
```

```sql
-- models/my_schema/user_events.sql
SELECT
    user_id,
    event_id,
    event_type,
    event_timestamp,
    properties
FROM raw_events
WHERE event_timestamp >= '2024-01-01'
```

Run with:
```bash
uv run t4t run ./examples/t_project
```

This will create an incremental table that:
- Uses merge strategy for upsert operations
- Automatically determines start date from existing data
- Includes 1-hour lookback for late-arriving events
- Updates existing records and inserts new ones
