# SQL Dialect Conversion

t4t automatically converts SQL between different database dialects, allowing you to write models in one dialect and run them on different databases.

## Overview

SQL dialect conversion is powered by [SQLglot](https://github.com/tobymao/sqlglot), a comprehensive SQL parser and transpiler. This enables you to:

- Write models in your preferred SQL dialect (e.g., PostgreSQL)
- Run the same models on different databases (e.g., Snowflake, DuckDB, BigQuery)
- Maintain a single source of truth for your SQL logic

## How It Works

### 1. Source Dialect Configuration

Configure your source dialect in `project.toml`:

```toml
[environments.dev.connection]
type = "duckdb"
path = "data/my_project.duckdb"

[flags]
source_dialect = "postgresql"  # Write models in PostgreSQL
```

### 2. Automatic Conversion

When you execute models, t4t:

1. Reads your SQL models (written in the source dialect)
2. Converts them to the target database dialect
3. Executes the converted SQL

The conversion happens automatically - you don't need to do anything special.

## Example

### Source SQL (PostgreSQL)

```sql
-- models/users.sql
SELECT 
    DATE_TRUNC('month', created_at) as month,
    COUNT(*) as user_count
FROM users
WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY DATE_TRUNC('month', created_at)
ORDER BY month DESC
```

### Converted to Snowflake

```sql
-- Automatically converted
SELECT 
    DATE_TRUNC('month', created_at) as month,
    COUNT(*) as user_count
FROM users
WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY DATE_TRUNC('month', created_at)
ORDER BY month DESC
```

### Converted to DuckDB

```sql
-- Automatically converted
SELECT 
    DATE_TRUNC('month', created_at) as month,
    COUNT(*) as user_count
FROM users
WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY DATE_TRUNC('month', created_at)
ORDER BY month DESC
```

## Supported Dialects

### Source Dialects (Write In)

You can write models in any of these dialects:

- **PostgreSQL** - Most commonly used
- **MySQL** - Popular open-source database
- **SQLite** - Lightweight embedded database
- **DuckDB** - Fast analytical database
- **Snowflake** - Cloud data warehouse
- **BigQuery** - Google's cloud data warehouse
- **SQL Server** - Microsoft's database
- **Oracle** - Enterprise database
- And many more via SQLglot

### Target Dialects (Run On)

t4t supports running on:

- **DuckDB** (default)
- **Snowflake**
- **PostgreSQL**
- **BigQuery**
- And any database with a t4t adapter

## Configuration

### Project-Level Configuration

Set the source dialect in `project.toml`:

```toml
[flags]
source_dialect = "postgresql"
```

### Environment Variables

```bash
export T4T_DB_SOURCE_DIALECT=postgresql
```

### Programmatic Configuration

```python
from t4t.adapters import AdapterConfig

config = AdapterConfig(
    type="duckdb",
    path="data/my_project.duckdb",
    source_dialect="postgresql"
)
```

## Common Conversions

### Date Functions

**PostgreSQL → Snowflake:**
```sql
-- PostgreSQL
DATE_TRUNC('month', created_at)

-- Snowflake (automatic)
DATE_TRUNC('month', created_at)
```

**PostgreSQL → DuckDB:**
```sql
-- PostgreSQL
DATE_TRUNC('month', created_at)

-- DuckDB (automatic)
DATE_TRUNC('month', created_at)
```

### String Functions

**PostgreSQL → Snowflake:**
```sql
-- PostgreSQL
UPPER(name) || '_' || LOWER(email)

-- Snowflake (automatic)
UPPER(name) || '_' || LOWER(email)
```

### Window Functions

Window functions are generally well-supported across dialects:

```sql
-- Works in PostgreSQL, Snowflake, DuckDB, BigQuery
SELECT 
    id,
    name,
    ROW_NUMBER() OVER (PARTITION BY category ORDER BY created_at) as row_num
FROM products
```

## Limitations

### Dialect-Specific Features

Some database-specific features may not convert perfectly:

- **Custom Functions**: Database-specific functions may need manual conversion
- **Advanced Features**: Some advanced SQL features may not be supported
- **Performance Hints**: Query hints are often database-specific

### Best Practices

1. **Use Standard SQL**: Stick to standard SQL features when possible
2. **Test Conversions**: Test your models on target databases
3. **Review Converted SQL**: Use verbose mode to see converted SQL
4. **Handle Edge Cases**: Some complex SQL may need manual adjustment

## Debugging Conversions

### Verbose Mode

See the converted SQL with verbose mode:

```bash
t4t run ./my_project -v
```

### Compile Command

Compile models to see conversion and analysis without execution:

```bash
t4t compile ./my_project
```

This will generate OTS modules and analysis files (including dependency graph) without executing models.

### Check Conversion Results

The execution results include conversion information:

```python
results = executor.execute_models(parser)
print(results['dialect_conversion'])
```

## Advanced Usage

### Custom Conversion Rules

For complex conversions, you can:

1. Write database-specific SQL in separate files
2. Use conditional logic in metadata files
3. Create custom adapters with specific conversion rules

### Multiple Source Dialects

You can mix dialects in the same project:

```sql
-- models/postgres_model.sql (PostgreSQL)
SELECT * FROM users WHERE created_at > NOW() - INTERVAL '1 day'
```

```sql
-- models/snowflake_model.sql (Snowflake)
SELECT * FROM users WHERE created_at > DATEADD(day, -1, CURRENT_TIMESTAMP)
```

Each model is converted to the target database as needed.

## Tips and Tricks

1. **Start with PostgreSQL**: PostgreSQL SQL is well-supported and converts well to most databases
2. **Use Standard Functions**: Prefer standard SQL functions over database-specific ones
3. **Test Early**: Test conversions early in development
4. **Review Output**: Always review converted SQL in verbose mode
5. **Document Exceptions**: Document any manual conversions needed

## Related Documentation

- [Database Adapters](database-adapters.md) - Learn about adapter system
- [Configuration](../getting-started/configuration.md) - Configuration options
- [Execution Engine](execution-engine.md) - How models are executed

