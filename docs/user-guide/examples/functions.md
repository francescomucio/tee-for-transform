# Function Examples

This guide provides practical examples of using User-Defined Functions (UDFs) in t4t.

## Example 1: Basic SQL Function

A simple function to calculate percentage:

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

```python
# functions/my_schema/calculate_percentage.py
metadata = {
    "function_name": "calculate_percentage",
    "description": "Calculate percentage with null handling",
    "function_type": "scalar",
    "language": "sql",
    "parameters": [
        {"name": "numerator", "type": "FLOAT"},
        {"name": "denominator", "type": "FLOAT"}
    ],
    "return_type": "FLOAT",
    "deterministic": True
}
```

Using it in a model:

```sql
-- models/revenue_analysis.sql
SELECT 
    product_id,
    sales,
    costs,
    my_schema.calculate_percentage(sales, costs) as profit_margin
FROM sales_data
```

## Example 2: Python Function with Decorator

A Python function that generates SQL:

```python
# functions/my_schema/format_currency.py
from t4t.parser.processing.function_decorator import functions

@functions.sql()
def format_currency(amount: float, currency: str = "USD") -> str:
    """
    Format amount as currency string.
    
    Args:
        amount: The amount to format
        currency: Currency code (default: USD)
    
    Returns:
        Formatted currency string
    """
    currency_symbols = {
        "USD": "$",
        "EUR": "€",
        "GBP": "£"
    }
    symbol = currency_symbols.get(currency, currency)
    return f"CONCAT('{symbol}', CAST({amount} AS VARCHAR))"
```

## Example 3: Database-Specific Override

Different implementations for different databases:

```sql
-- functions/my_schema/calculate_percentage.sql (Generic)
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

```sql
-- functions/my_schema/calculate_percentage.snowflake.sql (Snowflake-specific)
CREATE OR REPLACE FUNCTION my_schema.calculate_percentage(
    numerator FLOAT,
    denominator FLOAT
) RETURNS FLOAT
LANGUAGE SQL
AS $$
    SELECT CASE 
        WHEN denominator = 0 THEN NULL
        ELSE (numerator / denominator) * 100
    END
$$;
```

```sql
-- functions/my_schema/calculate_percentage.duckdb.sql (DuckDB-specific)
CREATE OR REPLACE MACRO my_schema.calculate_percentage(numerator, denominator) AS (
    CASE 
        WHEN denominator = 0 THEN NULL
        ELSE (numerator / denominator) * 100
    END
);
```

## Example 4: Function Dependencies

A function that depends on another function:

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

```sql
-- functions/my_schema/calculate_metric.sql
CREATE OR REPLACE FUNCTION my_schema.calculate_metric(value FLOAT) 
RETURNS FLOAT AS $$
    SELECT my_schema.calculate_percentage(value, 100.0) * 2.0
$$;
```

t4t automatically creates `calculate_percentage` before `calculate_metric`.

## Example 5: Function Testing

### Assertion-Based Test

```sql
-- tests/functions/test_calculate_percentage.sql
SELECT 
    my_schema.calculate_percentage(10.0, 20.0) = 50.0 AS test_passed
```

### Expected Value Test

```python
# functions/my_schema/calculate_percentage.py
metadata = {
    "function_name": "calculate_percentage",
    "tests": [
        {
            "name": "test_calculate_percentage",
            "expected": 50.0,
            "params": {"numerator": 10.0, "denominator": 20.0}
        },
        {
            "name": "test_calculate_percentage_zero",
            "expected": None,
            "params": {"numerator": 10.0, "denominator": 0.0}
        }
    ]
}
```

```sql
-- tests/functions/test_calculate_percentage.sql
SELECT 
    my_schema.calculate_percentage(@param1, @param2) AS result
```

```sql
-- tests/functions/test_calculate_percentage_zero.sql
SELECT 
    my_schema.calculate_percentage(@param1, @param2) IS NULL AS test_passed
```

## Example 6: Table-Valued Function

A function that returns a table (Snowflake example):

```sql
-- functions/my_schema/get_top_products.sql
CREATE OR REPLACE FUNCTION my_schema.get_top_products(
    limit_count INT
) RETURNS TABLE (
    product_id INT,
    product_name VARCHAR,
    sales FLOAT
) AS $$
    SELECT 
        product_id,
        product_name,
        SUM(sales) as sales
    FROM sales_data
    GROUP BY product_id, product_name
    ORDER BY sales DESC
    LIMIT limit_count
$$;
```

```python
# functions/my_schema/get_top_products.py
metadata = {
    "function_name": "get_top_products",
    "description": "Get top N products by sales",
    "function_type": "table",
    "language": "sql",
    "parameters": [
        {"name": "limit_count", "type": "INT"}
    ],
    "return_table_schema": [
        {"name": "product_id", "type": "INT"},
        {"name": "product_name", "type": "VARCHAR"},
        {"name": "sales", "type": "FLOAT"}
    ]
}
```

Using it in a model:

```sql
-- models/top_products_report.sql
SELECT * FROM my_schema.get_top_products(10)
```

## Example 7: Complex Function with Multiple Dependencies

```sql
-- functions/my_schema/normalize_value.sql
CREATE OR REPLACE FUNCTION my_schema.normalize_value(value FLOAT) 
RETURNS FLOAT AS $$
    SELECT CASE 
        WHEN value < 0 THEN 0
        WHEN value > 100 THEN 100
        ELSE value
    END
$$;
```

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

```sql
-- functions/my_schema/calculate_normalized_percentage.sql
CREATE OR REPLACE FUNCTION my_schema.calculate_normalized_percentage(
    numerator FLOAT,
    denominator FLOAT
) RETURNS FLOAT AS $$
    SELECT my_schema.normalize_value(
        my_schema.calculate_percentage(numerator, denominator)
    )
$$;
```

The execution order will be:
1. `normalize_value`
2. `calculate_percentage`
3. `calculate_normalized_percentage`

## Example 8: Function with Tags

```python
# functions/my_schema/calculate_percentage.py
metadata = {
    "function_name": "calculate_percentage",
    "description": "Calculate percentage with null handling",
    "function_type": "scalar",
    "language": "sql",
    "parameters": [
        {"name": "numerator", "type": "FLOAT"},
        {"name": "denominator", "type": "FLOAT"}
    ],
    "return_type": "FLOAT",
    "tags": ["calculation", "math", "analytics"],
    "object_tags": {
        "department": "analytics",
        "owner": "data-team",
        "pii": "false"
    }
}
```

Tags can be used for organization, filtering, and database-level tagging (where supported).

## Complete Project Example

See the `examples/t_project` and `examples/t_project_sno` directories for complete working examples with functions, models, and tests.


