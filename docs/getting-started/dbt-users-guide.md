# t4t for dbt Users

This guide helps dbt users understand t4t by mapping familiar dbt concepts to their t4t equivalents. Whether you're evaluating t4t or migrating an existing dbt project, this guide covers what you need to know.

## Concept Mapping

| dbt Concept | t4t Equivalent | Notes |
|---|---|---|
| **Model** (`.sql`) | **Model** (`.sql` or `.py`) | t4t supports both SQL and Python model files |
| **`ref('model_name')`** | **Plain table reference** | Use the table name directly (e.g., `FROM my_table`); t4t resolves dependencies automatically |
| **`source('schema', 'table')`** | **t4t source** | Declared in model metadata; referenced by table name |
| **`{{ config(...) }}`** | **Python metadata** | Model configuration is Python-based, not Jinja-based |
| **`schema.yml` / `schema.yaml`** | **Python metadata files** | Per-model `.py` files with typed `ModelMetadata` dicts |
| **`dbt_project.yml`** | **`project.toml`** | Project-level configuration in TOML format |
| **`profiles.yml`** | **`project.toml` `[environments.<name>.connection]`** | Database connection settings in the project config |
| **`dbt test`** | **`t4t test`** | Run data quality tests |
| **`dbt run`** | **`t4t run`** | Execute models |
| **`dbt build`** | **`t4t build`** | Run models + tests interleaved |
| **`dbt docs generate`** | **`t4t docs`** | Generate documentation site |
| **`dbt seed`** | **`t4t seed`** | Load static data (CSV, JSON, TSV) |
| **`dbt compile`** | **`t4t compile`** | Compile/analyze without executing |
| **`dbt debug`** | **`t4t debug`** | Test database connectivity |
| **`dbt init`** | **`t4t init`** | Scaffold a new project |
| **Jinja templates** | **Python** | No Jinja in t4t; use Python for logic, SQL for queries |
| **Macros** | **UDFs / Python functions** | SQL macros become SQL UDFs; complex macros become Python functions |
| **Tests (singular/generic)** | **`@test` decorator / SQL tests** | Python `@test` functions or SQL files in `tests/` |
| **Tags** | **Tags** | Similar tag-based model selection |
| **Hooks** | **N/A (yet)** | Not currently supported |
| **Snapshots** | **SCD2 materialization** | Set `"materialization": "scd2"` in model metadata — no separate artifact type or command needed |
| **Exposures** | **N/A (yet)** | Not currently supported |
| **Analysis** | **N/A (yet)** | Not currently supported |

## Key Differences

### No Jinja

t4t does **not** use Jinja templating in SQL files. Instead:

- **SQL models** are pure SQL — no `{{ }}`, no `{% %}`.
- **Python models** use the `@model` decorator to define transformations with full Python logic.
- **Variables** use `@variable_name` syntax in SQL, or are passed via `--vars` on the CLI.
- **Dynamic SQL** is generated in Python, not in Jinja templates.

**Example: dbt model with Jinja**
```sql
-- dbt: models/customers.sql
SELECT *
FROM {{ ref('orders') }}
WHERE {{ var('date_filter', '1=1') }}
```

**Equivalent t4t model**
```sql
-- t4t: models/customers.sql
SELECT *
FROM orders
WHERE @date_filter
```

Or as a Python model:
```python
# t4t: models/customers.py
from t4t.parser.processing.model import model

@model(description="Customer orders")
def customers():
    return "SELECT * FROM orders WHERE @date_filter"
```

### Python-Based Metadata

Instead of `schema.yml` files, t4t uses Python metadata files alongside each model:

```python
# models/customers.py
from t4t.typing import ModelMetadata

metadata: ModelMetadata = {
    "table_name": "analytics.customers",
    "description": "Customer overview",
    "schema": [
        {"name": "customer_id", "datatype": "string", "description": "Unique ID"},
        {"name": "total_orders", "datatype": "integer"},
    ],
    "tests": ["row_count_gt_0"],
    "tags": ["production", "marts"],
}
```

### Dependency Resolution

In dbt, you explicitly declare dependencies with `ref()`. In t4t, the parser **automatically** detects table references in your SQL and builds the dependency graph. You just write the table name.

### Multiple Models Per File

A single Python file can define multiple models, tests, and shared logic:

```python
# models/marts.py
from t4t.parser.processing.model import model

@model(table_name="analytics.customers", description="Customer summary")
def customers():
    return "SELECT customer_id, COUNT(*) as orders FROM orders GROUP BY 1"

@model(table_name="analytics.products", description="Product summary")
def products():
    return "SELECT product_id, SUM(amount) as revenue FROM order_items GROUP BY 1"
```

### Database Adapters

t4t supports multiple backends with automatic SQL dialect conversion:

| Backend | Status |
|---|---|
| **DuckDB** | ✅ Mature (default, included) |
| **MotherDuck** | ✅ Mature |
| **Snowflake** | ✅ Mature |
| **PostgreSQL** | 🚧 In progress |
| **BigQuery** | 🚧 In progress |

## Migration Steps

### Step 1: Install t4t

```bash
pip install t4t
```

> **Note**: t4t requires **Python 3.14+**. Make sure your environment meets this requirement.

### Step 2: Import Your dbt Project

t4t includes a built-in dbt importer:

```bash
t4t import ./my_dbt_project ./my_t4t_project
```

This converts:
- SQL models → t4t SQL models
- Jinja templates → Converted or Python models
- Tests → t4t tests
- Macros → UDFs (where possible)
- Seeds → Copied to `seeds/`
- Configuration → `project.toml`

Review the generated `IMPORT_REPORT.md` for details on what was converted and any warnings.

### Step 3: Review and Adjust

1. **Check the import report**: `cat ./my_t4t_project/IMPORT_REPORT.md`
2. **Review Python models**: Complex Jinja may need manual adjustment
3. **Update connection config**: Edit `project.toml` if needed
4. **Test the project**: `t4t test ./my_t4t_project`
5. **Run models**: `t4t run ./my_t4t_project`

### Step 4: Manual Conversion (if not using import)

If you prefer to convert manually:

1. **Create a new project**:
   ```bash
   t4t init my_t4t_project
   ```

2. **Copy SQL models** to `models/`, removing Jinja syntax:
   - Replace `{{ ref('model_name') }}` with the table name
   - Replace `{{ source('schema', 'table') }}` with `schema.table`
   - Replace `{{ var('name', 'default') }}` with `@name` and pass via `--vars`
   - Remove `{{ config(...) }}` and move settings to Python metadata

3. **Add metadata** in Python files alongside each model

4. **Convert tests** to t4t format (SQL tests in `tests/` or `@test` decorators)

5. **Convert macros** to SQL UDFs or Python functions

### Step 5: Run and Verify

```bash
# Test database connection
t4t debug ./my_t4t_project

# Run all models
t4t run ./my_t4t_project

# Run tests
t4t test ./my_t4t_project

# Build (models + tests interleaved)
t4t build ./my_t4t_project

# Generate documentation
t4t docs ./my_t4t_project
```

## Common Migration Patterns

### `ref()` → Direct Table Reference

```sql
-- dbt
SELECT * FROM {{ ref('orders') }}

-- t4t
SELECT * FROM orders
```

### `source()` → Schema-qualified Table

```sql
-- dbt
SELECT * FROM {{ source('raw', 'users') }}

-- t4t
SELECT * FROM raw.users
```

### `var()` → `@variable`

```sql
-- dbt
WHERE date >= '{{ var("start_date", "2024-01-01") }}'

-- t4t
WHERE date >= @start_date
```

Pass variables at runtime:
```bash
t4t run ./my_project --vars '{"start_date": "2024-01-01"}'
```

### `config()` → Python Metadata

```sql
-- dbt: {{ config(materialized='table', schema='marts') }}
```

```python
# t4t: models/marts/customers.py
metadata: ModelMetadata = {
    "table_name": "marts.customers",
    "materialization": "table",
}
```

### Tests → `@test` Decorator or SQL Tests

```sql
-- dbt: tests/assert_positive_total.sql
SELECT * FROM orders WHERE total < 0
```

```python
# t4t: tests/assert_positive_total.py
from t4t.testing import test

@test(description="Orders should have positive totals")
def assert_positive_total():
    return "SELECT * FROM orders WHERE total < 0"
```

Or as a SQL test file:
```sql
-- t4t: tests/assert_positive_total.sql
SELECT * FROM orders WHERE total < 0
```

## What t4t Does Better

- **Python-native**: Full Python for metadata, logic, and code generation — no Jinja to learn
- **Rich metadata**: Type-safe, Python-based model and column metadata
- **Dimensional modeling**: First-class support for facts, dimensions, and lookups
- **Multiple models per file**: Define many models in a single Python module
- **SQL dialect conversion**: Write once, run on any supported database
- **OTS support**: Export/import Open Transformation Specification modules
- **No separate test framework**: Tests are part of the model definition
- **SCD2 as a materialization**: History tracking is a per-model config, not a separate snapshot artifact with its own command

## What dbt Does Better (for now)

- **Ecosystem**: Larger community, more packages, more adapters
- **Hooks**: Pre/post hook support
- **Exposures**: Downstream consumer documentation
- **Analysis**: Ad-hoc analysis queries
- **Maturity**: Battle-tested in production at scale

## Next Steps

- [Quick Start](../getting-started/quickstart.md) — Get started in 5 minutes
- [dbt Import Guide](../user-guide/dbt-import.md) — Detailed import instructions
- [dbt Import Limitations](../user-guide/dbt-import-limitations.md) — Known limitations
- [Data Quality Tests](../user-guide/data-quality-tests.md) — Testing in t4t
- [CLI Reference](../user-guide/cli-reference.md) — Complete command reference
