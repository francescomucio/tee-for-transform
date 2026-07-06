# Seeds

Seeds allow you to load static data files (CSV, JSON, TSV) into your database tables before running your models. This is useful for reference data, lookup tables, or any static data that your models depend on.

## Overview

The seeds functionality provides:
- **Automatic Discovery**: Automatically finds seed files in the `seeds/` folder
- **Multiple Formats**: Supports CSV, JSON, and TSV files
- **Schema Support**: Organize seeds by schema using subfolders
- **Explicit Loading**: Load seeds with `t4t seed` or automatically with `t4t build`
- **Standalone Command**: Load seeds independently with `t4t seed`

## Quick Start

### 1. Create a Seeds Folder

Create a `seeds/` folder in your project root:

```
my_project/
├── seeds/
│   ├── users.csv
│   ├── products.json
│   └── my_schema/
│       └── orders.tsv
├── models/
│   └── ...
└── project.toml
```

### 2. Add Seed Files

Place your data files in the `seeds/` folder. The table name will be the file name without the extension.

**Example: `seeds/users.csv`**
```csv
id,name,email
1,Alice,alice@example.com
2,Bob,bob@example.com
3,Charlie,charlie@example.com
```

**Example: `seeds/products.json`**
```json
[
  {"id": 1, "name": "Product A", "price": 10.99},
  {"id": 2, "name": "Product B", "price": 20.50},
  {"id": 3, "name": "Product C", "price": 15.75}
]
```

**Example: `seeds/orders.tsv`**
```tsv
id	amount	status
1	100.00	pending
2	200.50	completed
3	150.25	pending
```

### 3. Load Seeds

Seeds must be loaded explicitly using the `seed` command:

```bash
# Load seeds before running models
t4t seed ./my_project
t4t run ./my_project
```

Or load seeds and run models in one step:

```bash
t4t seed ./my_project && t4t run ./my_project
```

**Note**: The `build` command automatically loads seeds before building models, but `run` does not.

### 4. Use Seeds in Your Models

Once loaded, seeds are available as tables in your SQL models:

```sql
-- models/user_analytics.sql
SELECT
    u.id,
    u.name,
    COUNT(o.id) as order_count
FROM users u
LEFT JOIN orders o ON o.user_id = u.id
GROUP BY u.id, u.name
```

## Schema Support

You can organize seeds by schema using subfolders. The first subfolder name becomes the schema name.

### Example Structure

```
seeds/
├── users.csv                    → table: users
├── products.json                → table: products
└── my_schema/
    ├── orders.tsv               → table: my_schema.orders
    └── customers.csv             → table: my_schema.customers
```

### Usage in Models

When seeds are in a schema folder, reference them with the schema prefix:

```sql
-- models/order_summary.sql
SELECT
    o.id,
    o.amount,
    c.name as customer_name
FROM my_schema.orders o
JOIN my_schema.customers c ON c.id = o.customer_id
```

## File Formats

### CSV Files

CSV files must have a header row. The first row defines the column names.

**Example: `seeds/users.csv`**
```csv
id,name,email,created_at
1,Alice,alice@example.com,2024-01-01
2,Bob,bob@example.com,2024-01-02
```

**Notes:**
- First row must be headers
- Comma-separated values
- Supports quoted values with commas
- Empty files (header only) create empty tables

### TSV Files

TSV (Tab-Separated Values) files work like CSV but use tabs as delimiters.

**Example: `seeds/orders.tsv`**
```tsv
id	amount	status	created_at
1	100.00	pending	2024-01-01
2	200.50	completed	2024-01-02
```

**Notes:**
- First row must be headers
- Tab-separated values
- Useful for data with commas in values

### JSON Files

JSON files can contain either an array of objects or a single object.

**Array Format (Multiple Rows):**
```json
[
  {"id": 1, "name": "Product A", "price": 10.99},
  {"id": 2, "name": "Product B", "price": 20.50}
]
```

**Single Object Format (One Row):**
```json
{
  "key": "value",
  "setting": "enabled",
  "threshold": 100
}
```

**Notes:**
- Array format: Each object becomes a row
- Single object: Creates a table with one row
- All objects in an array should have the same keys (columns)

## Standalone Seed Command

You can load seeds independently without running models using the `seed` command:

```bash
# Load all seeds
t4t seed ./my_project

# With verbose output
t4t seed ./my_project -v
```

### Command Output

```
Loading seeds from project: ./my_project

Found 3 seed file(s):
  - users.csv → users
  - products.json → products
  - my_schema/orders.tsv → my_schema.orders

Connected to database: duckdb

Loading seeds...

==================================================
SEED LOADING RESULTS
==================================================

✅ Successfully loaded 3 seed(s):
  - users: 3 rows
  - products: 3 rows
  - my_schema.orders: 3 rows

✅ All seeds loaded successfully!
```

## Best Practices

### 1. Use Seeds for Reference Data

Seeds are ideal for:
- **Lookup tables**: Country codes, status mappings, category hierarchies
- **Configuration data**: Settings, thresholds, business rules
- **Small static datasets**: User lists, product catalogs, reference data
- **Test data**: Sample data for development and testing

### 2. Keep Seeds Small

Seeds are loaded into memory and should be relatively small. For large datasets:
- Use external tables or views
- Load via SQL models that read from external sources
- Consider incremental loading strategies

### 3. Organize with Schemas

Use schema folders to organize related seeds:

```
seeds/
├── reference/
│   ├── countries.csv
│   ├── currencies.json
│   └── timezones.tsv
├── configuration/
│   ├── settings.json
│   └── thresholds.csv
└── test_data/
    └── sample_users.csv
```

### 4. Version Control Seeds

Include seed files in version control:
- Seeds are part of your project's data model
- They define the structure and initial data
- Changes to seeds should be tracked and reviewed

### 5. Use Descriptive File Names

File names become table names, so use clear, descriptive names:

```
✅ Good:
- users.csv
- product_categories.json
- order_statuses.tsv

❌ Avoid:
- data.csv
- file1.json
- temp.tsv
```

## Database Support

### DuckDB (Optimized)

DuckDB uses native functions for efficient loading:
- `read_csv_auto()` for CSV files
- `read_json_auto()` for JSON files
- Automatic type inference
- Fast bulk loading

### Other Databases

For other databases (PostgreSQL, Snowflake, BigQuery), seeds are loaded using:
- Generic `CREATE TABLE` statements
- Row-by-row `INSERT` statements
- All columns created as `VARCHAR` (type inference not available)

**Note**: For best performance with large seed files, consider using database-specific bulk loading tools or loading seeds via SQL models.

## Troubleshooting

### Seeds Folder Not Found

If you see:
```
⚠️  Seeds folder not found: ./seeds
```

**Solution**: Create a `seeds/` folder in your project root.

### No Seed Files Found

If you see:
```
ℹ️  No seed files found in seeds folder
```

**Solution**:
- Check that files have `.csv`, `.json`, or `.tsv` extensions
- Verify files are in the `seeds/` folder (not subdirectories unless using schemas)

### Loading Errors

If seed loading fails:

1. **Check file format**: Ensure CSV/TSV files have headers
2. **Check JSON syntax**: Validate JSON files are properly formatted
3. **Check file encoding**: Use UTF-8 encoding
4. **Check database connection**: Verify database is accessible
5. **Check permissions**: Ensure database user can create tables

### Table Already Exists

Seeds use `CREATE OR REPLACE TABLE`, so existing tables will be replaced. This is intentional:
- Seeds are idempotent: running multiple times produces the same result
- Seeds are refreshed on each run
- If you need to preserve existing data, use SQL models instead

## Examples

### Example 1: Reference Data

**`seeds/reference/countries.csv`**
```csv
code,name,region
US,United States,North America
CA,Canada,North America
UK,United Kingdom,Europe
```

**Usage in model:**
```sql
-- models/user_by_country.sql
SELECT
    c.name as country,
    COUNT(u.id) as user_count
FROM users u
JOIN reference.countries c ON c.code = u.country_code
GROUP BY c.name
```

### Example 2: Configuration Data

**`seeds/config/settings.json`**
```json
{
  "max_users": 1000,
  "min_order_amount": 10.00,
  "enabled_features": ["feature_a", "feature_b"]
}
```

**Usage in model:**
```sql
-- models/validated_orders.sql
SELECT *
FROM orders
WHERE amount >= (SELECT min_order_amount FROM config.settings)
```

### Example 3: Test Data

**`seeds/test/sample_users.csv`**
```csv
id,name,email,role
1,Test User,test@example.com,admin
2,Test Admin,admin@example.com,admin
```

Useful for development and testing environments.

## Integration with Models

Load seeds **before** running models to make them available as dependencies:

```bash
# Step 1: Load seeds
t4t seed ./my_project

# Step 2: Run models (seeds are now available)
t4t run ./my_project
```

Then your models can reference seed tables:

```sql
-- models/enriched_orders.sql
SELECT
    o.id,
    o.amount,
    u.name as user_name,
    p.name as product_name
FROM orders o
JOIN users u ON u.id = o.user_id
JOIN products p ON p.id = o.product_id
```

**Note**: The `build` command automatically loads seeds, so you only need to run `t4t build ./my_project`.

## Advanced Usage

### Conditional Seed Loading

You can control seed loading by organizing seeds in different folders and using the seed command selectively:

```bash
# Load only production seeds
t4t seed ./my_project  # Loads all seeds

# Or use environment-specific seed folders
# seeds/production/
# seeds/development/
```

### Seed Dependencies

Seeds can reference other seeds if loaded in the correct order. The loader processes seeds in alphabetical order by schema and filename.

### Custom Seed Processing

For advanced use cases, you can:
1. Create SQL models that read from seed tables
2. Transform seed data using SQL
3. Combine multiple seeds into derived tables

```sql
-- models/enriched_users.sql
SELECT
    u.*,
    c.name as country_name,
    s.status as account_status
FROM users u
LEFT JOIN reference.countries c ON c.code = u.country_code
LEFT JOIN reference.statuses s ON s.code = u.status_code
```

## Summary

Seeds provide a simple way to load static reference data into your database:
- ✅ Automatic discovery of seed files
- ✅ Support for CSV, JSON, and TSV formats
- ✅ Schema organization with subfolders
- ✅ Explicit loading with `t4t seed` or automatic with `t4t build`
- ✅ Standalone command for testing

Use seeds for reference data, configuration, and small static datasets that your models depend on.
