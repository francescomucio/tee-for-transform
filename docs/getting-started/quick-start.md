# Quick Start

Get up and running with t4t in minutes. This guide will walk you through creating your first SQL model and executing it.

## 1. Create a Project

```bash
# Initialize a new t4t project
uv run t4t init my_tee_project

# Or specify a database type
uv run t4t init my_tee_project -d snowflake

# Initialize with MotherDuck (cloud DuckDB)
uv run t4t init my_tee_project -d motherduck
```

This creates the project structure with:
- `project.toml` - Configuration file with database connection template
- `models/` - SQL model files
- `tests/` - Data quality tests
- `seeds/` - Static data files (CSV, JSON, TSV)
- `data/` - Database files (for DuckDB projects only)

The generated `project.toml` includes:
```toml
project_folder = "my_tee_project"

[connection]
type = "duckdb"
path = "data/my_tee_project.duckdb"

[flags]
materialization_change_behavior = "warn"  # Options: "warn", "error", "ignore"
```

Then navigate to your project:
```bash
cd my_tee_project
```

## 2. Configure Database

Edit `project.toml` to configure your database connection. For DuckDB, the default configuration is already set up and ready to use. For other databases, update the connection settings:

**DuckDB (default):**
```toml
[connection]
type = "duckdb"
path = "data/my_tee_project.duckdb"  # or "md:my_database" for MotherDuck
```

**Snowflake:**
```toml
[connection]
type = "snowflake"
host = "YOUR_ACCOUNT.snowflakecomputing.com"
user = "YOUR_USERNAME"
password = "YOUR_PASSWORD"
role = "YOUR_ROLE"
warehouse = "YOUR_WAREHOUSE"
database = "YOUR_DATABASE"
```

**PostgreSQL:**
```toml
[connection]
type = "postgresql"
host = "localhost"
port = 5432
database = "my_tee_project"
user = "postgres"
password = "postgres"
```

**BigQuery:**
```toml
[connection]
type = "bigquery"
project = "YOUR_PROJECT_ID"
database = "my_tee_project"  # dataset name
```

**MotherDuck:**
```toml
[connection]
type = "duckdb"
path = "md:my_tee_project"
database = "my_tee_project"
schema = "main"

[connection.extra]
# MotherDuck access token (recommended: use MOTHERDUCK_TOKEN environment variable instead)
# motherduck_token = "your_motherduck_access_token_here"
```

**Note:** For MotherDuck, set your access token via the `MOTHERDUCK_TOKEN` environment variable:
```bash
export MOTHERDUCK_TOKEN='your_access_token_here'
```

## 3. Create Your First Model

The `models/` directory was already created by the `init` command. Add your first SQL model:

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

## 4. Execute Your Model

Use the CLI to run your models:

```bash
# Run all models in the project
uv run t4t run .
```

Or from the parent directory:

```bash
uv run t4t run my_tee_project
```

## What Happened?

1. **Parsing**: t4t analyzed your SQL model and identified dependencies
2. **Configuration**: Database settings were loaded from `project.toml`
3. **Execution**: Your model was executed in the correct order
4. **Results**: The model was materialized as a table in DuckDB
5. **Testing**: Tests (if defined) were automatically executed

## Adding Tests

### Standard Tests

Add tests to your model metadata:

```python
# models/users.py
metadata: ModelMetadata = {
    "schema": [
        {
            "name": "id",
            "datatype": "integer",
            "tests": ["not_null", "unique"]
        }
    ],
    "tests": ["row_count_gt_0"]
}
```

### Custom SQL Tests

Create SQL files in `tests/` folder:

```sql
-- tests/check_minimum_rows.sql
SELECT 1 as violation
FROM {{ table_name }}
GROUP BY 1
HAVING COUNT(*) < 5
```

Reference in metadata:
```python
"tests": ["check_minimum_rows"]
```

See [Data Quality Tests](../user-guide/data-quality-tests.md) for more information.

## Adding Seeds

You can load static data files (CSV, JSON, TSV) into your database:

```bash
# Create seeds folder
mkdir seeds

# Add a seed file
echo "id,name
1,Alice
2,Bob" > seeds/users.csv

# Load seeds explicitly before running models
t4t seed ./my_project
t4t run ./my_project
```

**Note**: The `build` command automatically loads seeds, but `run` requires explicit seed loading.

See [Seeds](../user-guide/seeds.md) for more information.

## Next Steps

- [Configuration](configuration.md) - Learn about advanced configuration options
- [Seeds](../user-guide/seeds.md) - Load static data files into your database
- [Database Adapters](../user-guide/database-adapters.md) - Explore multi-database support
- [Data Quality Tests](../user-guide/data-quality-tests.md) - Comprehensive testing guide
- [Tags and Metadata](../user-guide/tags-and-metadata.md) - Organize and filter models with tags
- [Examples](../user-guide/examples/README.md) - See more complex examples
