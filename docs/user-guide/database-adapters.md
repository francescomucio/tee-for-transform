# Database Adapters

t4t provides a powerful pluggable database adapter system that allows you to write SQL models in one dialect and run them on different databases with automatic SQL dialect conversion.

## Overview

The adapter system allows you to:
- Write SQL models in one dialect (e.g., PostgreSQL) and run them on different databases (e.g., Snowflake, BigQuery)
- Use database-specific features and optimizations
- Manage multiple database configurations
- Automatically convert SQL using SQLglot

## Quick Start

### 1. Basic Usage

```python
from t4t.engine import ModelExecutor, load_database_config

# Load configuration from pyproject.toml or environment variables
config = load_database_config("default")

# Create executor
executor = ModelExecutor("/path/to/project", config)

# Execute models
results = executor.execute_models(parser)
```

### 2. Configuration

Add to your `pyproject.toml`:

```toml
[tool.t4t.database]
type = "duckdb"
path = "data/my_project.db"
source_dialect = "postgresql"  # Write models in PostgreSQL, convert to DuckDB
```

Or use environment variables:

```bash
export T4T_DB_TYPE=duckdb
export T4T_DB_PATH=data/my_project.db
export T4T_DB_SOURCE_DIALECT=postgresql
```

## Supported Databases

### DuckDB
- **Dialect**: `duckdb`
- **Features**: Tables, Views, Materialized Views (as tables)
- **Configuration**:
  ```toml
  type = "duckdb"
  path = "database.db"  # or ":memory:" for in-memory
  ```

### MotherDuck
- **Dialect**: `duckdb` (same as DuckDB)
- **Features**: Tables, Views, Materialized Views (as tables) - same as DuckDB
- **Configuration**:
  ```toml
  type = "duckdb"
  path = "md:my_database"  # or "motherduck:my_database"
  ```
- **Authentication**: Set `MOTHERDUCK_TOKEN` environment variable:
  ```bash
  export MOTHERDUCK_TOKEN='your_access_token'
  ```
- **Note**: The adapter automatically detects MotherDuck connections when the path starts with `md:` or `motherduck:`. See [Configuration Guide](../getting-started/configuration.md) for more details.

### Snowflake
- **Dialect**: `snowflake`
- **Features**: Tables, Views, Materialized Views, External Tables, **Tag Support**
- **Configuration**:
  ```toml
  type = "snowflake"
  host = "account.snowflakecomputing.com"
  user = "username"
  password = "password"
  database = "database"
  warehouse = "warehouse"
  role = "role"
  ```
- **Tag Support**: Full support for both dbt-style tags and database object tags on tables, views, and schemas. See [Tags and Metadata](tags-and-metadata.md) for details.

### PostgreSQL
- **Dialect**: `postgresql`
- **Features**: Tables, Views, Materialized Views
- **Configuration**:
  ```toml
  type = "postgresql"
  host = "localhost"
  port = 5432
  database = "database"
  user = "user"
  password = "password"
  ```

## SQL Dialect Conversion

t4t automatically converts SQL between dialects using SQLglot, allowing you to write models in one dialect and run them on different databases.

For complete documentation on SQL dialect conversion, including configuration, examples, and best practices, see the [SQL Dialect Conversion Guide](sql-dialect-conversion.md).

## Materialization Types

Different databases support different materialization types:

| Type | DuckDB | Snowflake | PostgreSQL |
|------|--------|-----------|------------|
| Table | ✅ | ✅ | ✅ |
| View | ✅ | ✅ | ✅ |
| Materialized View | ✅ (as table) | ✅ | ✅ |
| External Table | ❌ | ✅ | ❌ |

## Advanced Usage

### Custom Adapter Configuration

```python
from t4t.engine.adapters import AdapterConfig

config = AdapterConfig(
    type="snowflake",
    host="account.snowflakecomputing.com",
    user="user",
    password="password",
    database="database",
    warehouse="warehouse",
    source_dialect="postgresql",
    extra={"external_location": "s3://bucket/path"}
)

executor = ModelExecutor("/path/to/project", config)
```

### Multiple Database Configurations

```toml
[tool.t4t.databases]

[tool.t4t.databases.dev]
type = "duckdb"
path = "dev.db"
source_dialect = "postgresql"

[tool.t4t.databases.prod]
type = "snowflake"
host = "prod.snowflakecomputing.com"
# ... other config
```

```python
# Use specific configuration
config = load_database_config("prod")
executor = ModelExecutor("/path/to/project", config)
```

### Testing Adapters

```python
from t4t.engine.adapters.testing import test_adapter
from t4t.engine.adapters import get_adapter

# Test adapter
adapter = get_adapter(config)
results = test_adapter(adapter)

print(f"Connection test: {results['connection']['success']}")
print(f"Dialect conversion: {results['dialect_conversion']['success']}")
```

## Creating Custom Adapters

To create a custom adapter:

1. Inherit from `DatabaseAdapter`:

```python
from t4t.engine.adapters.base import DatabaseAdapter, MaterializationType

class MyDatabaseAdapter(DatabaseAdapter):
    def get_default_dialect(self):
        return "mydb"

    def get_supported_materializations(self):
        return [MaterializationType.TABLE, MaterializationType.VIEW]

    def connect(self):
        # Implementation
        pass

    # ... implement other required methods
```

2. Register the adapter:

```python
from t4t.engine.adapters.registry import register_adapter

register_adapter("mydb", MyDatabaseAdapter)
```

## Migration from Legacy System

The new system is backward compatible. To migrate:

1. **Gradual Migration**: Use `ModelExecutor` alongside `ModelExecutor`
2. **Configuration**: Move database config to `pyproject.toml`
3. **Features**: Take advantage of dialect conversion and new features

```python
# Old way
from t4t.engine import ModelExecutor
executor = ModelExecutor("/path/to/project", {"type": "duckdb"})

# New way
from t4t.engine import ModelExecutor, load_database_config
config = load_database_config()
executor = ModelExecutor("/path/to/project", config)
```

## Troubleshooting

### Common Issues

1. **SQL Conversion Errors**: Check if the source dialect is supported
2. **Connection Failures**: Verify configuration and credentials
3. **Materialization Not Supported**: Check adapter capabilities

### Debugging

Enable debug logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Testing Connection

```python
executor = ModelExecutor("/path/to/project", config)
success = executor.test_connection()
print(f"Connection test: {'PASSED' if success else 'FAILED'}")
```

## Performance Considerations

- **Dialect Conversion**: Adds overhead but enables cross-database compatibility
- **Connection Pooling**: Not yet implemented but planned for future versions
- **Query Optimization**: Database-specific optimizations are applied automatically

## Future Enhancements

- Connection pooling
- Query result caching
- Advanced materialization strategies
- Real-time schema validation
- Performance monitoring and metrics
