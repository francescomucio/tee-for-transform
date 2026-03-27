# Overview

Welcome to t4t (Tee for Transform)! This guide provides an overview of t4t's core concepts, architecture, and how it fits into your data transformation workflow.

## What is t4t?

t4t is a Python framework for managing SQL data transformations with support for multiple database backends, automatic SQL dialect conversion, and rich metadata-driven modeling. It's designed to make data transformation workflows more efficient, maintainable, and portable.

**The "what if" vision**: What if a transformation tool supported functions? What if it allowed for richer metadata? What if data modeling was a priority?

## Core Concepts

### 1. SQL Models

SQL models are the building blocks of t4t. Each model is a SQL file that defines a transformation:

```sql
-- models/users.sql
SELECT 
    id,
    name,
    email,
    created_at
FROM source_users
WHERE active = true
```

Models are stored in the `models/` directory and can reference other models, creating a dependency graph.

### 2. User-Defined Functions (UDFs)

Functions allow you to encapsulate reusable business logic and calculations:

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

Functions are created before models are executed and can be used in your SQL models. See the [Functions Guide](functions.md) for more details.

### 3. Dependency Resolution

t4t automatically analyzes your SQL models to build a dependency graph. When you run models, t4t:

1. Parses all SQL files
2. Identifies table references and dependencies
3. Determines the correct execution order
4. Executes models in dependency order

This means you don't need to manually manage execution order - t4t handles it automatically.

### 4. Multi-Database Support

Write your SQL once and run it on different databases. t4t supports:

- **DuckDB** - Fast analytical database (default)
- **Snowflake** - Cloud data warehouse
- **PostgreSQL** - Open-source relational database
- **BigQuery** - Google's cloud data warehouse
- And more via the pluggable adapter system

### 5. SQL Dialect Conversion

Write your models in your preferred SQL dialect (e.g., PostgreSQL), and t4t automatically converts them to the target database dialect using SQLglot:

```sql
-- Write in PostgreSQL
SELECT DATE_TRUNC('month', created_at) as month
FROM users
```

```sql
-- Automatically converted to Snowflake
SELECT DATE_TRUNC('month', created_at) as month
FROM users
```

### 5. Materialization Strategies

Models can be materialized in different ways:

- **Views** - Virtual tables (default)
- **Tables** - Physical tables
- **Incremental** - Efficient updates with append, merge, or delete+insert strategies

### 6. Metadata and Tags

Rich metadata support allows you to:

- Define column types and constraints
- Add tags for organization and filtering
- Attach database object tags (Snowflake)
- Configure tests and validations

### 7. Data Quality Tests

Built-in testing framework with:

- Standard tests: `not_null`, `unique`, `accepted_values`, `relationships`, `row_count_gt_0`, `row_count_eq`
- Custom SQL tests
- Severity levels: `error` or `warning` (configured in metadata files)
- Automatic test execution after model runs

## Architecture

t4t follows a modular, pluggable architecture:

```
┌─────────────────────────────────────────────────────────┐
│                      CLI Layer                           │
│  (t4t commands: run, parse, test, build, seed, etc.)    │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│                  Execution Layer                         │
│  • ProjectParser - Parses SQL and builds dependencies   │
│  • ModelExecutor - Executes models in order             │
│  • TestExecutor - Runs data quality tests               │
│  • SeedLoader - Loads static data files                │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│                  Adapter Layer                           │
│  • Database Adapters (DuckDB, Snowflake, PostgreSQL)   │
│  • SQL Dialect Conversion (SQLglot)                     │
│  • Connection Management                                │
└─────────────────────────────────────────────────────────┘
```

### Key Components

1. **CLI** (`tee/cli/`) - Command-line interface for all operations
2. **Parser** (`tee/parser/`) - SQL parsing, dependency analysis, and graph building
3. **Engine** (`tee/engine/`) - Model execution and state management
4. **Adapters** (`tee/adapters/`) - Database-specific implementations
5. **Testing** (`tee/testing/`) - Data quality testing framework

## Workflow

A typical t4t workflow:

1. **Initialize Project**
   ```bash
   t4t init my_project
   ```

2. **Create Models**
   - Write SQL files in `models/` directory
   - Add metadata files (`.py`) for configuration

3. **Run Models**
   ```bash
   t4t run ./my_project
   ```
   - Parses models
   - Builds dependency graph
   - Executes in correct order
   - Runs tests

4. **Test Data Quality**
   ```bash
   t4t test ./my_project
   ```

5. **Build with Tests**
   ```bash
   t4t build ./my_project
   ```
   - Runs models and tests interleaved
   - Stops on first ERROR severity test failure

## Key Features

### Multi-Database Support
Write once, run anywhere. t4t automatically handles SQL dialect conversion.

### Dependency-Aware Execution
No manual ordering needed - t4t figures out the correct execution order.

### Incremental Materialization
Efficient data processing with append, merge, and delete+insert strategies.

### Rich Metadata Support
Python-based metadata configuration with full type safety.

### Comprehensive Tagging
dbt-style tags and database object tags for tables, views, and schemas.

### Pluggable Architecture
Easy to add new database adapters.

### Configuration Management
Flexible configuration via `project.toml`.

## Comparison with Other Tools

### vs. dbt
- **Similar**: SQL-based transformations, dependency management, testing
- **Different**: Python metadata (vs. YAML), built-in SQL dialect conversion, pluggable adapters

### vs. Airflow
- **Similar**: Workflow orchestration, dependency management
- **Different**: SQL-first (vs. Python-first), simpler for SQL transformations, built-in testing

### vs. Custom Scripts
- **Similar**: Flexibility
- **Different**: Automatic dependency resolution, built-in testing, multi-database support, metadata management

## Getting Started

Ready to get started? Check out:

1. [Quick Start Guide](../getting-started/quick-start.md) - Get up and running in minutes
2. [CLI Reference](cli-reference.md) - Complete command reference
3. [Examples](examples/README.md) - Practical usage examples

## Next Steps

- [Functions](functions.md) - Learn about User-Defined Functions (UDFs)
- [Execution Engine](execution-engine.md) - Learn how models are executed
- [Database Adapters](database-adapters.md) - Explore multi-database support
- [Data Quality Tests](data-quality-tests.md) - Understand testing framework
- [Incremental Materialization](incremental-materialization.md) - Efficient data processing
- [Tags and Metadata](tags-and-metadata.md) - Organize and filter models

