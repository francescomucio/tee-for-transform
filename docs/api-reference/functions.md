# Function API Reference

This document provides API reference for working with functions in t4t.

## Function Decorators

### `@functions.sql()`

Decorator for SQL-generating functions. The decorated function should return a SQL expression string.

**Usage:**

```python
from t4t.parser.processing.function_decorator import functions

@functions.sql()
def calculate_percentage(numerator: float, denominator: float) -> float:
    return f"CASE WHEN {denominator} = 0 THEN NULL ELSE ({numerator} / {denominator}) * 100 END"
```

**Parameters:**
- `function_name` (str, optional): Override the function name (defaults to function name)
- `description` (str, optional): Function description
- `schema` (str, optional): Schema name for the function
- `database_name` (str, optional): Database-specific override
- `tags` (list, optional): List of tags
- `object_tags` (dict, optional): Dictionary of object tags

**Returns:**
- The decorated function, which can be called to generate SQL

### `@functions.python()`

Decorator for actual Python UDFs (for databases that support them, like Snowflake and BigQuery).

**Usage:**

```python
from t4t.parser.processing.function_decorator import functions

@functions.python()
def calculate_percentage(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return None
    return (numerator / denominator) * 100
```

**Parameters:**
- Same as `@functions.sql()`

**Returns:**
- The decorated function, which will be registered as a Python UDF

## Function Metadata

Function metadata is defined as a dictionary in a Python file:

```python
metadata = {
    "function_name": str,           # Required: Function name
    "description": str,             # Optional: Function description
    "function_type": str,           # Required: "scalar" or "table"
    "language": str,                # Required: "sql" or "python"
    "parameters": [                 # Required: List of parameter definitions
        {
            "name": str,            # Parameter name
            "type": str,            # Parameter type (e.g., "FLOAT", "INT")
            "description": str      # Optional: Parameter description
        }
    ],
    "return_type": str,             # Required for scalar functions: Return type
    "return_table_schema": [       # Required for table functions: Output schema
        {
            "name": str,            # Column name
            "type": str             # Column type
        }
    ],
    "deterministic": bool,          # Optional: Whether function is deterministic
    "tags": [str],                 # Optional: List of tags
    "object_tags": {               # Optional: Dictionary of object tags
        "key": "value"
    },
    "tests": [                     # Optional: List of test definitions
        {
            "name": str,            # Test name (must match SQL test file)
            "expected": Any,        # Optional: Expected value for expected value pattern
            "params": {             # Optional: Parameters for the test
                "param1": value1,
                "param2": value2
            },
            "severity": str         # Optional: "error" or "warning"
        }
    ]
}
```

## Function Discovery

Functions are automatically discovered from the `functions/` directory:

```
functions/
└── schema_name/
    ├── function_name.sql
    ├── function_name.py          # Metadata
    ├── function_name.snowflake.sql  # Database-specific override
    └── function_name.duckdb.sql     # Database-specific override
```

## Function Execution

Functions are executed automatically before models during the build process:

1. Functions are discovered and parsed
2. Dependencies are resolved
3. Functions are created in dependency order
4. Models are executed (can use functions)
5. Tests are executed for functions and models

## Function Testing API

### Test Definition

Tests are defined in function metadata:

```python
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

### Test SQL

Test SQL files are placed in `tests/functions/`:

```sql
-- tests/functions/test_calculate_percentage.sql
SELECT
    my_schema.calculate_percentage(@param1, @param2) AS result
```

### Test Placeholders

- `@function_name` or `{{ function_name }}` - The function name
- `@param1`, `@param2`, etc. - Function parameters from test metadata

## Function Parser API

### `FunctionSQLParser`

Parses SQL function definitions:

```python
from t4t.parser.parsers import FunctionSQLParser

parser = FunctionSQLParser(connection={"type": "duckdb"})

# Read SQL content
with open("functions/my_schema/calculate_percentage.sql", "r") as f:
    sql_content = f.read()

# Parse the SQL content
result = parser.parse(
    content=sql_content,
    file_path="functions/my_schema/calculate_percentage.sql",
    dialect="duckdb"  # Optional, inferred from connection if not provided
)
```

**Note:** The parser automatically looks for a companion Python metadata file (same name with `.py` extension) in the same directory. If found, metadata from the Python file will be merged with the SQL-extracted metadata.

### `FunctionPythonParser`

Parses Python function files:

```python
from t4t.parser.parsers import FunctionPythonParser

parser = FunctionPythonParser()
result = parser.parse(
    python_file_path="functions/my_schema/calculate_percentage.py"
)
```

## Function Execution API

### `ExecutionEngine.execute_functions()`

Execute functions in dependency order:

```python
from t4t.engine import ExecutionEngine

engine = ExecutionEngine(config=connection_config)
results = engine.execute_functions(
    parsed_functions=parsed_functions,
    execution_order=execution_order
)
```

**Returns:**
```python
{
    "executed_functions": [str],      # List of successfully executed function names
    "failed_functions": [              # List of failed functions
        {
            "function": str,           # Function name
            "error": str              # Error message
        }
    ],
    "execution_log": [str]            # Execution log entries
}
```

## Adapter Function API

### `DatabaseAdapter.create_function()`

Create a function in the database:

```python
adapter.create_function(
    function_name="my_schema.calculate_percentage",
    function_sql="CREATE OR REPLACE FUNCTION ...",
    metadata={...}
)
```

### `DatabaseAdapter.function_exists()`

Check if a function exists:

```python
exists = adapter.function_exists(
    function_name="my_schema.calculate_percentage",
    signature="FLOAT, FLOAT"  # Optional: For overload checking
)
```

### `DatabaseAdapter.drop_function()`

Drop a function:

```python
adapter.drop_function(
    function_name="my_schema.calculate_percentage",
    signature="FLOAT, FLOAT"  # Optional: For overloaded functions
)
```
