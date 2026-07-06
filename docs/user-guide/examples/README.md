# Examples

This section contains practical examples demonstrating t4t's capabilities.

## Available Examples

- [Basic Usage](basic-usage.md) - Common usage patterns and workflows
- [Functions](functions.md) - User-Defined Functions (UDFs) with complete examples
- [Incremental Example](incremental-example.md) - Complete incremental materialization example
- [Testing Example](testing-example.md) - Data quality testing with standard and custom SQL tests

## Quick Start Examples

### Basic SQL Model

```python
# models/my_table.py
from t4t.typing import ModelMetadata

metadata: ModelMetadata = {
    "description": "My first table",
    "materialization": "table"
}
```

```sql
-- models/my_table.sql
SELECT
    id,
    name,
    created_at
FROM source_table
WHERE status = 'active'
```

### Incremental Model

```python
# models/incremental_table.py
from t4t.typing import ModelMetadata

metadata: ModelMetadata = {
    "description": "Incremental table",
    "materialization": "incremental",
    "incremental": {
        "strategy": "merge",
        "merge": {
            "unique_key": ["id"],
            "filter_column": "updated_at",
            "start_value": "auto",
            "lookback": "1 hour"
        }
    }
}
```

```sql
-- models/incremental_table.sql
SELECT
    id,
    name,
    updated_at,
    status
FROM source_table
WHERE status = 'active'
```

## Running Examples

```bash
# Run all models
uv run t4t run ./t_project

# Run with variables (JSON format)
uv run t4t run ./t_project --vars '{"start_date": "2024-01-01"}'

# Run specific model
uv run t4t run ./t_project --select my_schema.my_table

# Run models by tag
uv run t4t run ./t_project --select tag:analytics

# Exclude models by tag
uv run t4t run ./t_project --exclude tag:test
```

## Example Projects

### Complete Project Structure

```
t_project/
├── models/
│   └── my_schema/
│       ├── my_table.sql
│       ├── my_table.py
│       ├── incremental_table.sql
│       └── incremental_table.py
├── functions/                    # User-Defined Functions
│   └── my_schema/
│       ├── calculate_percentage.sql
│       └── calculate_percentage.py
├── tests/
│   ├── my_custom_test.sql       # Model tests
│   ├── check_minimum_rows.sql   # Model tests
│   └── functions/               # Function tests
│       ├── test_calculate_percentage.sql
│       └── test_calculate_percentage_zero.sql
├── data/
│   ├── t_project.duckdb
│   └── t4t_state.db
└── project.toml
```

### Configuration

```toml
# project.toml
project_folder = "t_project"

[environments.dev.connection]
type = "duckdb"
path = "t_project/data/t_project.duckdb"
schema = "my_schema"

[flags]
materialization_change_behavior = "warn"
```

## Next Steps

- Explore the [Basic Usage Examples](basic-usage.md) for common patterns
- Learn about [Functions](functions.md) for creating reusable UDFs
- Try the [Incremental Example](incremental-example.md) for advanced data processing
- Learn about [Testing](testing-example.md) with standard and custom SQL tests
- Check the [Incremental Materialization Guide](../incremental-materialization.md) for detailed configuration options
- Learn about [Tags and Metadata](../tags-and-metadata.md) for organizing and filtering models
