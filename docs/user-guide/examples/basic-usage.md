# Basic Usage Examples

This page demonstrates common usage patterns with t4t, from simple single-model execution to complex multi-database workflows.

## Single Model Execution

Execute a single SQL model:

```python
from t4t.engine import ModelExecutor, load_database_config

# Load configuration
config = load_database_config()

# Create executor
executor = ModelExecutor("/path/to/project", config)

# Execute a single model
sql = """
SELECT
    id,
    name,
    email,
    created_at
FROM source_users
WHERE active = true
"""

result = executor.execute_single_model("active_users", sql)
print(f"Created table with {result['table_info']['row_count']} rows")
```

## Multi-Model Project

Execute multiple models with dependencies:

```python
from t4t.engine import ModelExecutor, load_database_config
from t4t.parser import ProjectParser

# Load configuration
config = load_database_config()

# Parse project
parser = ProjectParser("/path/to/project", config)
parsed_models = parser.collect_models()
execution_order = parser.get_execution_order()

# Execute all models
executor = ModelExecutor("/path/to/project", config)
results = executor.execute_models(parsed_models, execution_order)

print(f"Executed {len(results['executed_tables'])} models successfully")
```

## Cross-Database Migration

Write models in PostgreSQL and run on Snowflake:

```python
# Configuration for Snowflake with PostgreSQL source dialect
config = {
    "type": "snowflake",
    "host": "account.snowflakecomputing.com",
    "user": "username",
    "password": "password",
    "database": "analytics",
    "warehouse": "compute_wh",
    "source_dialect": "postgresql"  # Write in PostgreSQL
}

executor = ModelExecutor("/path/to/project", config)

# This PostgreSQL SQL will be automatically converted to Snowflake
sql = """
SELECT
    EXTRACT(YEAR FROM created_at) as year,
    COUNT(*) as user_count
FROM users
WHERE created_at >= '2023-01-01'
GROUP BY EXTRACT(YEAR FROM created_at)
ORDER BY year
"""

result = executor.execute_single_model("yearly_users", sql)
```

## Testing Database Connections

Test your database configuration:

```python
from t4t.engine import ModelExecutor, load_database_config

config = load_database_config()
executor = ModelExecutor("/path/to/project", config)

# Test connection
if executor.test_connection():
    print("✅ Database connection successful")

    # Get database info
    info = executor.get_database_info()
    print(f"Database: {info['database_type']}")
    print(f"Adapter: {info['adapter_type']}")
else:
    print("❌ Database connection failed")
```

## Error Handling

Handle execution errors gracefully:

```python
try:
    results = executor.execute_models(parsed_models, execution_order)

    # Check for failures
    if results["failed_tables"]:
        print("Some models failed:")
        for failure in results["failed_tables"]:
            print(f"  - {failure['table']}: {failure['error']}")

    # Check execution log
    for log_entry in results["execution_log"]:
        status = "✅" if log_entry["status"] == "success" else "❌"
        print(f"{status} {log_entry['table']}")

except Exception as e:
    print(f"Execution failed: {e}")
```

## Configuration Examples

### Development Environment

```toml
# pyproject.toml
[tool.t4t.database]
type = "duckdb"
path = "dev.db"
source_dialect = "postgresql"
```

### Production Environment

```toml
# pyproject.toml
[tool.t4t.database]
type = "snowflake"
host = "prod.snowflakecomputing.com"
user = "prod_user"
password = "${SNOWFLAKE_PASSWORD}"
database = "analytics"
warehouse = "prod_wh"
role = "analyst"
source_dialect = "postgresql"
```

### Multiple Environments

```toml
# pyproject.toml
[tool.t4t.databases]

[tool.t4t.databases.dev]
type = "duckdb"
path = "dev.db"
source_dialect = "postgresql"

[tool.t4t.databases.staging]
type = "snowflake"
host = "staging.snowflakecomputing.com"
# ... other config

[tool.t4t.databases.prod]
type = "snowflake"
host = "prod.snowflakecomputing.com"
# ... other config
```

```python
# Use specific environment
config = load_database_config("prod")
executor = ModelExecutor("/path/to/project", config)
```

## Next Steps

- [Database Adapters](../database-adapters.md) - Learn about multi-database support and adapters
- [Configuration](../../getting-started/configuration.md) - Advanced configuration options
- [Tags and Metadata](../tags-and-metadata.md) - Organize and filter models with tags
