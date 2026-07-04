# User-Defined Functions (UDFs)

t4t supports User-Defined Functions (UDFs) that can be used across your SQL models. Functions are created in the database before models are executed, allowing you to encapsulate reusable business logic and calculations.

## Overview

Functions in t4t are similar to models - they can be defined in SQL or Python, support metadata, and are automatically discovered and executed. Functions are created in dependency order, just like models, and can depend on other functions or tables.

## Function Types

### SQL Functions

SQL functions are defined using standard SQL `CREATE FUNCTION` syntax:

```sql
-- functions/my_schema/calculate_percentage.sql
CREATE OR REPLACE FUNCTION my_schema.calculate_percentage(
    numerator FLOAT,
    denominator FLOAT
) RETURNS FLOAT AS $$
    SELECT CASE 
        WHEN denominator = 0 THEN NULL
        ELSE (numerator / denominator) * 100
    END
$$;
```

### Python Functions

Python functions can generate SQL or define actual Python UDFs (for databases that support them):

```python
# functions/my_schema/calculate_percentage.py
from t4t.parser.processing.function_decorator import functions

@functions.sql()
def calculate_percentage(
    numerator: float,
    denominator: float
) -> float:
    """
    Calculate percentage with null handling.
    
    Args:
        numerator: The numerator value
        denominator: The denominator value
    
    Returns:
        Percentage value or None if denominator is zero
    """
    return f"""
        CASE 
            WHEN {denominator} = 0 THEN NULL
            ELSE ({numerator} / {denominator}) * 100
        END
    """
```

## Function Metadata

Functions can have metadata defined in a companion Python file:

```python
# functions/my_schema/calculate_percentage.py
metadata = {
    "function_name": "calculate_percentage",
    "description": "Calculate percentage with null handling",
    "function_type": "scalar",
    "language": "sql",
    "parameters": [
        {"name": "numerator", "type": "FLOAT", "description": "The numerator value"},
        {"name": "denominator", "type": "FLOAT", "description": "The denominator value"}
    ],
    "return_type": "FLOAT",
    "deterministic": True,
    "tags": ["calculation", "math"],
    "object_tags": {
        "department": "analytics",
        "owner": "data-team"
    }
}
```

## Function Execution

Functions are automatically executed before models during both `t4t run` and `t4t build` commands:

1. **Function Discovery**: Functions are discovered from the `functions/` directory
2. **Dependency Resolution**: Function dependencies are resolved (functions can depend on other functions or tables)
3. **Execution Order**: Functions are executed in dependency order before any models
4. **Test Execution**: During `t4t build`, function tests are executed immediately after each function is created
5. **Model Execution**: Models are executed after all functions are created

**Example Output:**
```
📦 Executing 1 function(s) before models...
  ✅ Executed 1 function(s)
    - my_schema.calculate_percentage
  🧪 Running tests for my_schema.calculate_percentage...
  ✅ Tests: 2 passed

📦 Executing: my_schema.my_first_table
  ✅ Model executed: 3 rows
```

## Function Organization

Functions are organized by schema, similar to models:

```
project/
├── functions/
│   ├── my_schema/
│   │   ├── calculate_percentage.sql
│   │   ├── calculate_percentage.py  # Metadata
│   │   ├── format_currency.sql
│   │   └── format_currency.py
│   └── analytics/
│       ├── calculate_metric.sql
│       └── calculate_metric.py
```

## Database-Specific Functions

You can provide database-specific implementations using override files:

```
functions/
└── my_schema/
    ├── calculate_percentage.sql          # Generic SQL
    ├── calculate_percentage.snowflake.sql # Snowflake-specific
    ├── calculate_percentage.py           # Metadata
```

The generic `.sql` file is used for all databases, while database-specific files (`.snowflake.sql`, `.duckdb.sql`, etc.) override the generic one for that specific database.

## Using Functions in Models

Once a function is defined, you can use it in your SQL models:

```sql
-- models/revenue_analysis.sql
SELECT 
    product_id,
    sales,
    costs,
    my_schema.calculate_percentage(sales, costs) as profit_margin
FROM sales_data
```

Functions are automatically created before models are executed, so you can reference them immediately.

## Function Dependencies

Functions can depend on other functions or tables:

```sql
-- functions/my_schema/calculate_metric.sql
CREATE OR REPLACE FUNCTION my_schema.calculate_metric(value FLOAT) 
RETURNS FLOAT AS $$
    SELECT my_schema.calculate_percentage(value, 100.0) * 2.0
$$;
```

t4t automatically resolves function dependencies and creates them in the correct order.

## Function Testing

Functions can be tested using SQL tests in the `tests/functions/` folder. This section provides an overview - see the [Data Quality Tests Guide](data-quality-tests.md#function-tests) for additional details on test execution and integration with the testing framework.

```sql
-- tests/functions/test_calculate_percentage.sql
SELECT 
    my_schema.calculate_percentage(10.0, 20.0) = 50.0 AS test_passed
```

### Test Patterns

#### Assertion-Based (Default)

The test SQL returns a boolean - `TRUE` means the test passed:

```sql
-- tests/functions/test_calculate_percentage.sql
SELECT 
    my_schema.calculate_percentage(10.0, 20.0) = 50.0 AS test_passed
```

#### Expected Value Pattern

The test SQL returns a value, and the expected value is specified in metadata:

```python
# functions/my_schema/calculate_percentage.py
metadata = {
    "function_name": "calculate_percentage",
    "tests": [
        {
            "name": "test_calculate_percentage",
            "expected": 50.0,
            "params": {"numerator": 10.0, "denominator": 20.0}
        }
    ]
}
```

```sql
-- tests/functions/test_calculate_percentage.sql
SELECT 
    my_schema.calculate_percentage(@param1, @param2) AS result
```

### Test Placeholders

Function tests support placeholders:

- `@function_name` or `{{ function_name }}` - The function name
- `@param1`, `@param2`, etc. - Function parameters from test metadata

## Function Decorators

When defining functions in Python, use decorators to specify the function type:

### `@functions.sql()`

For SQL-generating functions:

```python
@functions.sql()
def calculate_percentage(numerator: float, denominator: float) -> float:
    return f"CASE WHEN {denominator} = 0 THEN NULL ELSE ({numerator} / {denominator}) * 100 END"
```

### `@functions.python()`

For actual Python UDFs (Snowflake, BigQuery):

```python
@functions.python()
def calculate_percentage(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return None
    return (numerator / denominator) * 100
```

## Function Execution Order

Functions are executed in the following order:

1. **Seeds** - Load seed data into tables
2. **Functions** - Create functions in dependency order
3. **Models** - Execute models (can use functions)
4. **Tests** - Run tests for functions and models

## Function Overloading

Some databases (like Snowflake and DuckDB) support function overloading - multiple functions with the same name but different signatures. t4t supports this by allowing you to define multiple functions with the same name but different parameter types.

## Best Practices

1. **Use descriptive names**: Function names should clearly indicate their purpose
2. **Document parameters**: Always include parameter descriptions in metadata
3. **Handle edge cases**: Consider NULL values, division by zero, etc.
4. **Test thoroughly**: Write tests for your functions, especially edge cases
5. **Keep functions focused**: Each function should do one thing well
6. **Use schemas**: Organize functions by schema to avoid naming conflicts

## Examples

See the [Function Examples](examples/functions.md) guide for complete examples including:
- Basic SQL functions
- Python functions with decorators
- Database-specific overrides
- Function dependencies
- Function testing

