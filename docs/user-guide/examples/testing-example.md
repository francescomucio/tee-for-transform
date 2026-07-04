# Testing Example

This example demonstrates how to use t4t's data quality testing framework with both standard tests and custom SQL tests.

## Project Structure

```
t_project/
├── models/
│   └── my_schema/
│       ├── orders.sql
│       ├── orders.py
│       ├── users.sql
│       └── users.py
├── tests/
│   ├── check_minimum_rows.sql
│   └── column_not_negative.sql
└── project.toml
```

## Model with Standard Tests

**`models/my_schema/users.py`:**
```python
from t4t.typing import ModelMetadata

metadata: ModelMetadata = {
    "description": "Users table",
    "materialization": "table",
    "schema": [
        {
            "name": "user_id",
            "datatype": "integer",
            "description": "Unique user identifier",
            "tests": ["not_null", "unique"]
        },
        {
            "name": "email",
            "datatype": "string",
            "description": "User email address",
            "tests": ["not_null", "unique"]
        },
        {
            "name": "status",
            "datatype": "string",
            "description": "User status",
            "tests": [
                {
                    "name": "accepted_values",
                    "params": {"values": ["active", "inactive", "pending"]}
                }
            ]
        },
        {
            "name": "created_at",
            "datatype": "timestamp",
            "description": "Account creation timestamp",
            "tests": ["not_null"]
        }
    ],
    "tests": [
        "row_count_gt_0",
        "unique"  # Checks entire row uniqueness (all columns)
    ]
}
```

**`models/my_schema/users.sql`:**
```sql
SELECT 
    user_id,
    email,
    status,
    created_at
FROM source_users
WHERE deleted_at IS NULL
```

## Model with Custom SQL Tests

**`models/my_schema/orders.py`:**
```python
from t4t.typing import ModelMetadata

metadata: ModelMetadata = {
    "description": "Orders table",
    "materialization": "table",
    "schema": [
        {
            "name": "order_id",
            "datatype": "integer",
            "tests": ["not_null", "unique"]
        },
        {
            "name": "user_id",
            "datatype": "integer",
            "tests": [
                "not_null",
                {
                    "name": "relationships",
                    "params": {
                        "to": "my_schema.users",
                        "field": "user_id"
                    }
                }
            ]
        },
        {
            "name": "amount",
            "datatype": "number",
            "tests": [
                "not_null",
                "column_not_negative"  # Custom SQL test
            ]
        },
        {
            "name": "status",
            "datatype": "string",
            "tests": [
                {
                    "name": "accepted_values",
                    "params": {"values": ["pending", "completed", "cancelled"]}
                }
            ]
        }
    ],
    "tests": [
        "row_count_gt_0",
        {
            "name": "check_minimum_rows",
            "params": {"min_rows": 10}  # Custom SQL test with parameters
        }
    ]
}
```

**`models/my_schema/orders.sql`:**
```sql
SELECT 
    o.order_id,
    o.user_id,
    o.amount,
    o.status,
    o.created_at
FROM source_orders o
WHERE o.deleted_at IS NULL
```

## Custom SQL Tests

### Model-Level Test: Check Minimum Rows

**`tests/check_minimum_rows.sql`:**
```sql
-- Check that a table has at least a minimum number of rows
-- Accepts min_rows parameter (defaults to 10)
-- Returns rows when test fails (0 rows = pass, 1+ rows = fail)

SELECT 1 as violation
FROM {{ table_name }}
GROUP BY 1
HAVING COUNT(*) < {{ min_rows | default(10) }}
```

### Column-Level Test: Check for Negative Values

**`tests/column_not_negative.sql`:**
```sql
-- Check that a numeric column has no negative values
-- Returns rows when test fails (0 rows = pass, 1+ rows = fail)

SELECT {{ column_name }}
FROM {{ table_name }}
WHERE {{ column_name }} < 0
```

## Running Tests

### Run Models (Tests Execute Automatically)

```bash
t4t run t_project
```

Output:
```
==================================================
EXECUTING SQL MODELS
==================================================

Executing 2 models in dependency order...
Execution order: my_schema.users -> my_schema.orders

Execution Results:
  Successfully executed: 2 tables
  Failed: 0 tables

==================================================
EXECUTING TESTS
==================================================

Test Results:
  Total tests: 12
  ✅ Passed: 12
  ❌ Failed: 0

✅ All tests passed!
```

### Run Tests Independently

```bash
t4t test t_project
```

Output:
```
==================================================
EXECUTING TESTS
==================================================

Test Results:
  Total tests: 12
  ✅ Passed: 12
  ❌ Failed: 0

✅ All tests passed!
```

### Run Tests

```bash
t4t test t_project
```

Test severity is configured in metadata files. To make a test a warning instead of an error, set the `severity` field to `"warning"` in the test's metadata.

## Test Results Breakdown

For the example above, you would see:

**Standard Tests:**
- ✅ `not_null` on `user_id`, `email`, `status`, `created_at`, `order_id`, `amount`
- ✅ `unique` on `user_id`, `email`, `order_id`
- ✅ `accepted_values` on `status` (both tables)
- ✅ `relationships` on `orders.user_id` → `users.user_id`
- ✅ `row_count_gt_0` on both tables
- ✅ `unique` on `users` (entire row uniqueness)

**Custom SQL Tests:**
- ✅ `column_not_negative` on `orders.amount`
- ✅ `check_minimum_rows` on `orders` (with min_rows=10)

## Parameterized Custom Tests

### Advanced Example: Data Freshness Check

**`tests/data_freshness.sql`:**
```sql
-- Check that data is recent (within max_age_hours)
-- Accepts: date_column (required), max_age_hours (default: 24)

SELECT 1 as violation
FROM {{ table_name }}
WHERE {{ date_column }} < CURRENT_TIMESTAMP - INTERVAL '{{ max_age_hours | default(24) }}' HOUR
```

**Usage:**
```python
metadata: ModelMetadata = {
    "tests": [
        {
            "name": "data_freshness",
            "params": {
                "date_column": "updated_at",
                "max_age_hours": 12
            }
        }
    ]
}
```

### Column Range Check

**`tests/column_in_range.sql`:**
```sql
-- Check that column values are within a range
-- Accepts: min_value (default: 0), max_value (required)

SELECT {{ column_name }}
FROM {{ table_name }}
WHERE {{ column_name }} < {{ min_value | default(0) }}
   OR {{ column_name }} > {{ max_value }}
```

**Usage:**
```python
metadata: ModelMetadata = {
    "schema": [
        {
            "name": "score",
            "datatype": "number",
            "tests": [
                {
                    "name": "column_in_range",
                    "params": {"min_value": 0, "max_value": 100}
                }
            ]
        }
    ]
}
```

## Best Practices

1. **Use standard tests for common checks** - They're optimized and well-tested
2. **Use SQL tests for custom business logic** - When standard tests don't cover your needs
3. **Document your SQL tests** - Add comments explaining parameters and logic
4. **Use parameters for flexibility** - Make tests reusable across different thresholds
5. **Test in CI/CD** - Include `t4t test` in your pipeline

## Troubleshooting

### Test Not Found

If you see:
```
⚠️  Test 'my_custom_test' not implemented yet
```

Check:
1. SQL file exists in `tests/` folder
2. File name matches test name (without `.sql` extension)
3. File is readable and has valid SQL

### Variable Substitution Issues

If variables aren't being substituted:
1. Use `{{ variable_name }}` syntax (recommended)
2. Ensure variable name matches exactly (case-sensitive)
3. Check that `table_name` and `column_name` are available (for column tests)

### Test Always Fails

If test always returns rows:
1. Check your SQL logic - should return 0 rows when passing
2. Verify variable substitution is working correctly
3. Test the SQL query manually against your data

## Next Steps

- [Data Quality Tests Guide](../data-quality-tests.md) - Complete testing documentation
- [Execution Engine](../execution-engine.md) - Learn about model execution
- [Basic Usage](basic-usage.md) - More examples

