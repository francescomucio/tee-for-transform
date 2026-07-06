# Tags and Metadata

t4t supports comprehensive tagging functionality for organizing, categorizing, and managing your data transformations. Tags can be attached at multiple levels: individual tables/views, and entire schemas/modules.

## Overview

t4t supports two types of tags:

1. **dbt-style tags** (`tags`): List of strings used for filtering, categorization, and model selection
   - Example: `tags = ["analytics", "production", "fct"]`
   - Used for: Model selection (`--select tag:analytics`), filtering, organization

2. **Database object tags** (`object_tags`): Key-value pairs attached directly to database objects
   - Example: `object_tags = {"sensitivity_tag": "pii", "classification": "public"}`
   - Used for: Data governance, compliance, database-level metadata

## Table and View Tags

Tags can be attached to individual tables and views through model metadata.

### Python Models

```python
# models/users.py
from t4t.parser.processing.model import model

@model(
    table_name="users",
    description="User dimension table",
    tags=["analytics", "production", "dim"],  # dbt-style tags
    object_tags={  # database-style tags
        "sensitivity_tag": "pii",
        "classification": "public",
        "data_owner": "analytics-team"
    }
)
def users_model():
    return "SELECT * FROM source.users"
```

### Dynamic Model Creation

For creating multiple similar models without code repetition, use `create_model()`:

```python
# models/staging.py
from t4t.parser.processing.model import create_model

# Define table names to create models for
STAGING_TABLES = ["users", "orders", "products"]
STAGING_SCHEMA = "staging"

# Dynamically create models for each staging table
for table_name in STAGING_TABLES:
    create_model(
        table_name=table_name,
        sql=f"SELECT * FROM {STAGING_SCHEMA}.{table_name}",
        description=f"Select from {STAGING_SCHEMA}.{table_name}",
        tags=["staging", "raw"]
    )
```

**Benefits:**
- **Zero code repetition**: Just update the list to add/remove models
- **Consistent patterns**: All models follow the same structure
- **Easy maintenance**: Change the pattern once, apply to all models

**When to use `create_model()` vs `@model` decorator:**
- Use `create_model()` when you have many similar models that follow a pattern
- Use `@model` decorator when each model has unique logic or complex transformations

**Example with metadata:**

```python
# models/marts.py
from t4t.parser.processing.model import create_model

MART_TABLES = [
    {"name": "daily_sales", "source": "sales", "tags": ["daily", "sales"]},
    {"name": "monthly_revenue", "source": "revenue", "tags": ["monthly", "finance"]},
    {"name": "user_metrics", "source": "users", "tags": ["daily", "analytics"]},
]

for table in MART_TABLES:
    create_model(
        table_name=table["name"],
        sql=f"""
        SELECT
            *,
            CURRENT_TIMESTAMP() as updated_at
        FROM staging.{table["source"]}
        """,
        description=f"Mart table for {table['name']}",
        tags=table["tags"],
        object_tags={
            "source_table": table["source"],
            "refresh_frequency": "daily" if "daily" in table["tags"] else "monthly"
        }
    )
```

### SQL Models with Metadata

```python
# models/users.py
metadata = {
    "description": "User dimension table",
    "tags": ["analytics", "production"],  # dbt-style tags
    "object_tags": {  # database-style tags
        "sensitivity_tag": "pii",
        "classification": "public"
    }
}
```

```sql
-- models/users.sql
SELECT
    id,
    name,
    email,
    created_at
FROM source_users
```

### Using Tags for Model Selection

Tags can be used to filter models during execution:

```bash
# Run only models with "analytics" tag
uv run t4t run ./my_project --select tag:analytics

# Run models excluding "test" tag
uv run t4t run ./my_project --exclude tag:test

# Combine tag and name selection
uv run t4t run ./my_project --select tag:production my_schema.users
```

## Schema-Level Tags

Tags can be attached to entire schemas/modules, which is useful for applying common metadata to all tables in a schema. Schema-level tags are configured in `project.toml`.

### Method 1: Per-Schema Configuration (Recommended)

Configure tags for specific schemas:

```toml
# project.toml
project_folder = "my_project"

[environments.dev.connection]
type = "snowflake"
# ... connection config

[schemas.my_schema]
tags = ["analytics", "production"]  # dbt-style tags
object_tags = {  # database-style tags
    "sensitivity_tag" = "pii"
    "classification" = "public"
    "data_owner" = "analytics-team"
}

[schemas.staging_schema]
tags = ["staging", "test"]
object_tags = {
    "classification" = "internal"
}
```

**Benefits:**
- Different tags per schema
- Fine-grained control
- Clear organization

### Method 2: Module-Level Configuration

Apply tags to all schemas in the project:

```toml
# project.toml
project_folder = "my_project"

[environments.dev.connection]
type = "snowflake"
# ... connection config

[module]
tags = ["analytics", "production"]  # Applied to all schemas
object_tags = {  # Applied to all schemas
    "sensitivity_tag" = "pii"
    "classification" = "public"
}
```

**Benefits:**
- Consistent tagging across all schemas
- Simple configuration
- Good for single-purpose projects

### Method 3: Root-Level Tags

Simple root-level tags (dbt-style only):

```toml
# project.toml
project_folder = "my_project"

[environments.dev.connection]
type = "snowflake"
# ... connection config

tags = ["analytics", "production"]  # Applied to all schemas
```

**Benefits:**
- Simplest configuration
- Quick setup
- Limited to dbt-style tags only

### Precedence Order

When multiple configuration methods are used, precedence is:

1. **Per-schema tags** (`[schemas.schema_name]`) - Highest priority
2. **Module-level tags** (`[module]`) - Medium priority
3. **Root-level tags** (`tags = [...]`) - Lowest priority

Per-schema configuration always overrides module-level or root-level tags.

## Tag Merging

Tags are merged intelligently:

- **Table/View tags**: Transformation-specific tags are merged with module-level tags
- **Schema tags**: Per-schema tags override module-level tags
- **Deduplication**: Duplicate tags are automatically removed (case-insensitive)

### Example: Tag Merging

```toml
# project.toml
[module]
tags = ["analytics", "production"]

[schemas.my_schema]
tags = ["fct"]  # This will override module tags for my_schema
```

```python
# models/users.py
@model(
    table_name="users",
    tags=["dim"]  # This will be merged with schema tags
)
def users_model():
    return "SELECT * FROM source.users"
```

**Result for `my_schema.users`:**
- Schema tags: `["fct"]` (overrides module tags)
- Table tags: `["dim"]`
- Final tags: `["fct", "dim"]` (merged)

## Database Support

### Snowflake

Snowflake has **full support** for both tag types:

- **dbt-style tags**: Converted to Snowflake tags (e.g., `tee_tag_analytics = "analytics"`)
- **object_tags**: Attached directly as key-value pairs (e.g., `sensitivity_tag = "pii"`)

Tags are attached using Snowflake's `ALTER TABLE/VIEW/SCHEMA SET TAG` syntax.

**Example:**
```sql
-- dbt-style tags create:
ALTER TABLE my_schema.users SET TAG tee_tag_analytics = 'analytics';
ALTER TABLE my_schema.users SET TAG tee_tag_production = 'production';

-- object_tags create:
ALTER TABLE my_schema.users SET TAG sensitivity_tag = 'pii';
ALTER TABLE my_schema.users SET TAG classification = 'public';
```

### Other Databases

Other databases (DuckDB, PostgreSQL, etc.) support tag extraction and storage in OTS format, but tags are **not attached to database objects** (since they don't have native tag support).

Tags are still available for:
- Model selection (`--select tag:analytics`)
- OTS export
- Metadata tracking

## Complete Example

Here's a complete example showing all tag features:

### project.toml

```toml
project_folder = "analytics_project"

[environments.dev.connection]
type = "snowflake"
host = "account.snowflakecomputing.com"
user = "analyst"
password = "${SNOWFLAKE_PASSWORD}"
database = "analytics"
warehouse = "compute_wh"
role = "analyst"

[module]
tags = ["analytics"]  # Default for all schemas
object_tags = {
    "data_owner" = "analytics-team"
}

[schemas.fct]
tags = ["fct", "production"]  # Override for fct schema
object_tags = {
    "classification" = "public"
    "data_owner" = "analytics-team"
}

[schemas.dim]
tags = ["dim", "production"]
object_tags = {
    "classification" = "public"
    "sensitivity_tag" = "pii"  # Dimensions may contain PII
}
```

### Model with Tags

```python
# models/fct/orders.py
from t4t.parser.processing.model import model

@model(
    table_name="orders",
    description="Fact table for orders",
    tags=["daily"],  # Additional tag specific to this model
    object_tags={
        "refresh_frequency": "daily",
        "source_system": "ecommerce"
    }
)
def orders_model():
    return """
    SELECT
        order_id,
        user_id,
        order_date,
        total_amount
    FROM source.orders
    """
```

**Result:**
- **Schema tags**: `["fct", "production"]` (from `[schemas.fct]`)
- **Table tags**: `["daily"]` (from model)
- **Final tags**: `["fct", "production", "daily"]` (merged)
- **Schema object_tags**: `{"classification": "public", "data_owner": "analytics-team"}`
- **Table object_tags**: `{"refresh_frequency": "daily", "source_system": "ecommerce"}`

All tags are attached to the `fct.orders` table in Snowflake.

## Best Practices

### 1. Use Consistent Tag Naming

```toml
# Good: Consistent naming
tags = ["analytics", "production", "fct"]

# Avoid: Inconsistent naming
tags = ["analytics", "PRODUCTION", "Fct"]  # Case-sensitive duplicates
```

### 2. Use Per-Schema Tags for Multi-Schema Projects

```toml
[schemas.fct]
tags = ["fct", "production"]

[schemas.dim]
tags = ["dim", "production"]

[schemas.staging]
tags = ["staging", "test"]
```

### 3. Use Module-Level Tags for Single-Schema Projects

```toml
[module]
tags = ["analytics", "production"]
```

### 4. Use object_tags for Data Governance

```toml
[schemas.pii_schema]
object_tags = {
    "sensitivity_tag" = "pii"
    "gdpr_applicable" = "true"
    "retention_days" = "365"
}
```

### 5. Combine Both Tag Types

```python
@model(
    table_name="users",
    tags=["analytics", "dim"],  # For filtering/selection
    object_tags={  # For data governance
        "sensitivity_tag": "pii",
        "classification": "public",
        "data_owner": "analytics-team"
    }
)
```

## Troubleshooting

### Tags Not Appearing in Database

**Issue**: Tags are configured but not appearing in Snowflake.

**Solutions:**
1. Check adapter support: Only Snowflake currently attaches tags to database objects
2. Verify permissions: Ensure the Snowflake user has `CREATE TAG` and `APPLY TAG` privileges
3. Check logs: Enable debug logging to see tag attachment attempts

```bash
uv run t4t run ./my_project -v
```

### Schema Tags Not Applied

**Issue**: Schema-level tags are configured but not attached.

**Solutions:**
1. Verify schema name matches: `[schemas.my_schema]` must match the actual schema name
2. Check precedence: Per-schema tags override module-level tags
3. Ensure schema is created: Tags are attached when the schema is first created

### Tag Selection Not Working

**Issue**: `--select tag:analytics` doesn't find models.

**Solutions:**
1. Verify tags are in metadata: Check `parsed_models.json` to see if tags are extracted
2. Check tag format: Tags should be lists of strings in metadata
3. Use correct syntax: `--select tag:analytics` (not `--select tags:analytics`)

## Related Documentation

- [Configuration](../getting-started/configuration.md) - Project configuration
- [Database Adapters](database-adapters.md) - Database-specific features
- [Execution Engine](execution-engine.md) - Model execution and selection
