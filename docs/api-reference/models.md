# Model API Reference

This document provides API reference for working with models in t4t.

## Model Decorator

### `@model`

Decorator for marking Python functions as SQL models.

**Usage:**

```python
from t4t.parser.processing.model import model

@model(
    table_name="users",
    description="User dimension table",
    tags=["analytics", "production"],
    variables=["env", "debug"]
)
def users_model():
    return "SELECT * FROM source.users"
```

**Parameters:**
- `table_name` (str, optional): Custom table name. If not provided, uses function name.
- `description` (str, optional): Model description
- `variables` (list[str], optional): List of variable names to inject into the function's namespace
- `tags` (list[str], optional): dbt-style tags for filtering and organization
- `object_tags` (dict, optional): Database object tags (key-value pairs)
- `**metadata` (Any): Additional metadata to store with the model

**Returns:**
- The decorated function with model metadata stored as `_model_metadata` attribute

**Example with variables:**

```python
@model(
    table_name="users",
    variables=["env", "debug"]
)
def users_model():
    # Variables are injected into the function's namespace
    return f"SELECT * FROM source.users WHERE environment = '{env}'"
```

## Model Factory

### `create_model()`

Dynamically create a model without using a decorator. Useful for creating multiple similar models programmatically.

**Usage:**

```python
from t4t.parser.processing.model import create_model

# Simple example
create_model(
    table_name="users",
    sql="SELECT * FROM staging.users",
    description="Select from staging.users"
)

# In a loop for multiple models
STAGING_TABLES = ["users", "orders", "products"]
STAGING_SCHEMA = "staging"

for table_name in STAGING_TABLES:
    create_model(
        table_name=table_name,
        sql=f"SELECT * FROM {STAGING_SCHEMA}.{table_name}",
        description=f"Select from {STAGING_SCHEMA}.{table_name}",
        tags=["staging", "raw"]
    )
```

**Parameters:**
- `table_name` (str, required): Name of the table/model to create
- `sql` (str, required): SQL query string
- `description` (str, optional): Model description
- `variables` (list[str], optional): List of variable names (extracted by AST parser)
- `tags` (list[str], optional): dbt-style tags
- `object_tags` (dict, optional): Database object tags
- `**metadata` (Any): Additional metadata

**Returns:**
- `None` (models are registered via AST parsing)

**Note:**
The parser extracts model information via AST analysis, so this function primarily serves as a validation and documentation marker. The parser reads the source code directly, not the runtime values.

**Example with metadata:**

```python
create_model(
    table_name="daily_sales",
    sql="""
    SELECT 
        *,
        CURRENT_TIMESTAMP() as updated_at
    FROM staging.sales
    """,
    description="Daily sales mart table",
    tags=["daily", "sales", "mart"],
    object_tags={
        "source_table": "staging.sales",
        "refresh_frequency": "daily",
        "data_owner": "analytics-team"
    }
)
```

## SqlModelMetadata (Auto-Instantiation)

### Automatic Model Creation from Metadata

For Python files that define a `metadata` variable and have a companion `.sql` file, t4t can automatically instantiate `SqlModelMetadata` without requiring explicit instantiation.

**Usage:**

```python
# models/my_schema/my_view.py
from t4t.typing.metadata import ModelMetadata

metadata: ModelMetadata = {
    "materialization": "view",
    "schema": [
        {"name": "id", "datatype": "number", "description": "ID column"}
    ]
}

# No explicit 'model = SqlModelMetadata(metadata)' needed!
# t4t will automatically detect and instantiate it
```

**Companion SQL file:**
```sql
-- models/my_schema/my_view.sql
SELECT id, name FROM my_schema.my_first_table
```

**How it works:**
1. The parser detects a `metadata` variable in the Python file
2. Checks if a companion `.sql` file exists (same name, different extension)
3. If both conditions are met and no model was already registered from this file, automatically instantiates `SqlModelMetadata`
4. The model is registered and ready to use

**Error Handling:**
- **Model conflicts**: If a model with the same name already exists from a different file, a warning is logged
- **SQL parsing errors**: If the companion SQL file has invalid syntax, a warning is logged
- **Other errors**: Logged at debug level (expected in some cases)

**When to use:**
- You have companion `.py` and `.sql` files
- You want the simplest possible syntax (just define `metadata`)
- You prefer separating SQL code from Python metadata

**Explicit instantiation still works:**
If you prefer explicit control, you can still use:
```python
from t4t.parser.processing.model_builder import SqlModelMetadata

metadata: ModelMetadata = {...}
model = SqlModelMetadata(metadata)  # Explicit instantiation
```

## When to Use Each

### Use `@model` decorator when:
- Each model has unique logic or complex transformations
- You need fine-grained control over individual models
- Models have different patterns or structures
- SQL is generated dynamically in Python

### Use `create_model()` when:
- You have many similar models that follow a pattern
- You want to reduce code repetition
- Models can be generated from a list or configuration
- You're creating staging or intermediate tables with similar structures
- SQL is embedded in Python code

### Use `SqlModelMetadata` (auto-instantiation) when:
- You have companion `.py` and `.sql` files
- You want the simplest syntax (just define `metadata`)
- You prefer separating SQL code from Python metadata
- SQL is in a separate `.sql` file

## Model Metadata

Both decorators create models with the following metadata structure:

```python
{
    "table_name": str,           # Model/table name
    "function_name": str,        # Function name (for @model)
    "description": str | None,   # Model description
    "variables": list[str],       # Variables to inject
    "tags": list[str],            # dbt-style tags
    "object_tags": dict,          # Database object tags
    "metadata": dict,             # Additional metadata
    "needs_evaluation": bool,     # Whether SQL needs evaluation
    "sql": str | None            # SQL string (for create_model)
}
```

## Dimension shorthand and automatic registry

For facts, column metadata may include a **`dimension`** string so the parser, dependency graph, dimensional graph, docs site, and default relationship tests can resolve a target dimension table without repeating `fk_to` on every column.

- **Logical name**: `dim_date` → logical key `date`; `dimension: "date"` resolves to that model’s fully qualified name (same schema convention as your project layout).
- **Grain / level**: `dimension: "date.month"` resolves from the auto-built registry. By default, a level slug comes from **`hierarchy.levels[].name`** on the dimension model (e.g. `"Month"` → `month`) and points at **that** table.
- **Separate physical table for a grain** (e.g. `dim_month` for month while `dim_date` holds the day hierarchy): on the physical model set **`conformed_dimension`** with **`logical`** (parent logical name, e.g. `date`) and **`level`** (slug, e.g. `month`). That registers `date.month` → that model and **overrides** the hierarchy-only mapping from another table.
- **Which models count as dimensions**: `table_type` is **`dim`**, **`dimension`** (treated as dim), or the model short name starts with **`dim_`**.
- **No manual config file**: The mapping is built automatically after models are parsed. Duplicate **base** logical keys from two different dimension models (e.g. two `dim_date` → both `date`) raise an error; composite keys can be disambiguated with **`conformed_dimension`**.

**Troubleshooting:** After parse, the registry is written to **`output/dimension_registry.json`** when you use **`t4t debug`** or **`ProjectParser.save_to_json()`**, and is included in **`export_all`** / compile JSON exports alongside `parsed_models.json`.

For joins that do not match this convention, use explicit **`fk_to`** on the column (`table` + `column`).

## Related Documentation

- [Tags and Metadata](../user-guide/tags-and-metadata.md) - Comprehensive guide to tags and metadata
- [Execution Engine](../user-guide/execution-engine.md) - Running models
- [CLI Reference](../user-guide/cli-reference.md) - Command-line usage

