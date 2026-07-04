# Importing dbt Projects

This guide explains how to import dbt projects into t4t format, including step-by-step instructions, best practices, and troubleshooting.

## Overview

The `t4t import` command converts dbt projects to t4t format, preserving models, tests, macros, seeds, and configuration. The importer handles:

- ✅ SQL models with Jinja templates
- ✅ Data quality tests (standard, generic, and singular)
- ✅ Macros (converted to UDFs where possible)
- ✅ **Package dependencies** (automatically downloaded and macros expanded)
- ✅ Seeds (CSV, JSON, TSV files)
- ✅ Project configuration (`dbt_project.yml` → `project.toml`)
- ✅ Connection configuration (`profiles.yml` → `project.toml`)
- ✅ Schema resolution and organization
- ✅ Variables extraction and documentation

## Quick Start

### Basic Import

```bash
# Import a dbt project
t4t import ./my_dbt_project ./imported_project

# Check the import report
cat ./imported_project/IMPORT_REPORT.md
```

### Import to OTS Format

```bash
# Import directly to OTS format
t4t import ./my_dbt_project ./imported_project --format ots

# OTS modules will be in output/ots_modules/
ls ./imported_project/output/ots_modules/
```

## Step-by-Step Guide

### 1. Prepare Your dbt Project

Ensure your dbt project is complete and valid:

```bash
# Test your dbt project first
cd my_dbt_project
dbt debug
dbt compile
```

### 2. Run the Import

```bash
# Basic import
t4t import ./my_dbt_project ./imported_project

# With verbose output to see progress
t4t import ./my_dbt_project ./imported_project -v
```

### 3. Review the Import Report

After import, check the generated report:

```bash
# View the import report
cat ./imported_project/IMPORT_REPORT.md

# Or open in your editor
code ./imported_project/IMPORT_REPORT.md
```

The report includes:
- Summary statistics
- Validation results
- Model conversion details
- Warnings and unsupported features
- Variables documentation

### 4. Validate the Imported Project

```bash
# Validate syntax, dependencies, and metadata
cd imported_project
t4t debug .

# Or use dry-run to validate before importing
t4t import ./my_dbt_project ./imported_project --dry-run
```

### 5. Test the Imported Project

```bash
# Test the imported project
cd imported_project
t4t test .

# Run models
t4t run .
```

## Common Use Cases

### Selective Import

Import only specific models:

```bash
# Import only production models
t4t import ./my_dbt_project ./imported_project \
  --select tag:production

# Import specific models
t4t import ./my_dbt_project ./imported_project \
  --select customers --select orders

# Exclude test models
t4t import ./my_dbt_project ./imported_project \
  --exclude tag:test --exclude *_test
```

### Preserve Original Filenames

Keep dbt's original file names:

```bash
t4t import ./my_dbt_project ./imported_project \
  --preserve-filenames
```

**Note:** By default, files are renamed to match final table names (after schema/alias resolution).

### Gradual Migration with Jinja

Keep Jinja templates for gradual migration:

```bash
t4t import ./my_dbt_project ./imported_project \
  --keep-jinja
```

This preserves Jinja templates (except `ref()` and `source()` which are converted). Requires Jinja2 support in t4t (coming soon).

### Custom Schema and Dialect

Specify default schema and target dialect:

```bash
t4t import ./my_dbt_project ./imported_project \
  --default-schema analytics \
  --target-dialect snowflake
```

## Import Process Details

### What Gets Converted

#### Models
- SQL models → t4t SQL models
- Jinja templates → Converted or Python models
- Model metadata → Python metadata files (always created, even without metadata)
  - Always includes `table_name` field
  - Includes `TODO: Add model description` if no description found
- Schema resolution → Folder structure (`models/{schema}/{table}.sql`)
- Aliases → Handled from `{{ config(alias='...') }}` or `schema.yml` (highest priority)

#### Tests
- Standard tests → t4t standard tests
- Generic tests → t4t generic tests
- Singular tests → t4t SQL tests
- Source freshness tests → Skipped with warnings

#### Macros
- Simple SQL macros → SQL UDFs
- Complex macros → Documented in report
- Macro calls → UDF calls (where possible)

#### Seeds
- CSV/JSON/TSV files → Copied to `seeds/`
- Seed metadata → Preserved

#### Configuration
- `dbt_project.yml` → `project.toml`
- `profiles.yml` → Connection config in `project.toml`
- Variables → Documented in import report

### Schema Resolution

The importer follows dbt's schema resolution priority:

1. Model file config (`{{ config(schema='...') }}`)
2. `schema.yml` metadata
3. `dbt_project.yml` (most specific match)
4. Profile schema (from `profiles.yml`)
5. Default schema (`dev` if no profile, or `--default-schema`)

**Alias Resolution:**
- Aliases are resolved with the same priority as schemas
- `{{ config(alias='custom_name') }}` (highest priority)
- `schema.yml` alias field
- Model file name (default)

Models are organized into folders matching their resolved schema:
```
models/
├── analytics/
│   ├── customers.sql
│   └── orders.sql
└── staging/
    └── raw_data.sql
```

### Jinja Conversion

The importer handles Jinja templates as follows:

**Simple Conversions:**
- `{{ ref('model_name') }}` → Fully qualified table name
- `{{ source('schema', 'table') }}` → `schema.table`
- `{{ var('var_name', 'default') }}` → t4t variable syntax

**Complex Jinja:**
- Loops, complex conditionals → Python models
- Unconvertible macros → Python models with TODOs
- Conversion failures → Logged in import report

**With `--keep-jinja`:**
- Only `ref()` and `source()` are converted
- Other Jinja is preserved (requires Jinja2 support in t4t)

### Metadata Files

Every SQL model gets a corresponding Python metadata file (`.py`) created automatically:

**Structure:**
```python
# Model metadata converted from dbt
from t4t.typing import ModelMetadata

metadata: ModelMetadata = {
    "table_name": "schema.table_name",  # Always included
    "description": "Model description or TODO: Add model description",
    "schema": [...],  # Column definitions (if available)
    # ... other metadata fields
}
```

**Key Points:**
- Metadata files are **always created**, even if no metadata exists in dbt
- `table_name` is **always included** (required for validation)
- If no description is found, `"TODO: Add model description"` is added
- All `.py` files end with a newline (POSIX standard)
- Aliases from dbt are reflected in the `table_name` field

**Example - Model with metadata:**
```python
metadata: ModelMetadata = {
    "table_name": "marts.customers",
    "description": "Customer overview data mart",
    "schema": [
        {"name": "customer_id", "datatype": "string", "description": "Unique ID"},
        # ...
    ],
}
```

**Example - Model without metadata:**
```python
metadata: ModelMetadata = {
    "table_name": "marts.locations",
    "description": "TODO: Add model description",
}
```

## Troubleshooting

### Common Issues

#### 1. "dbt_project.yml not found"

**Problem:** The importer can't find `dbt_project.yml` in the source folder.

**Solution:**
```bash
# Ensure you're pointing to the dbt project root
t4t import ./my_dbt_project ./imported_project

# Check that dbt_project.yml exists
ls ./my_dbt_project/dbt_project.yml
```

#### 2. "profiles.yml not found"

**Problem:** Connection configuration can't be extracted.

**Solution:**
- The importer looks for `profiles.yml` in:
  - `~/.dbt/profiles.yml` (default)
  - `$DBT_PROFILES_DIR/profiles.yml`
  - Project directory
- If not found, a default DuckDB connection is used
- You can manually update `project.toml` after import

#### 3. "Model conversion failed"

**Problem:** Some models failed to convert.

**Solution:**
1. Check `IMPORT_REPORT.md` for details
2. Look for warnings in the conversion log
3. Complex Jinja may require manual conversion
4. Check `CONVERSION_LOG.json` for error details

#### 4. "Validation errors found"

**Problem:** Imported project has validation errors.

**Solution:**
```bash
# Run validation to see details
cd imported_project
t4t debug . -v

# Check IMPORT_REPORT.md for validation results
cat IMPORT_REPORT.md
```

Common validation issues:
- SQL syntax errors (check SQL files)
- Missing dependencies (check model references)
- Missing metadata (check metadata files)

**Note:** All models get metadata files (`.py`) created automatically, even if no metadata was found in dbt. These files include:
- `table_name`: The final resolved table name (schema.table format)
- `description`: Either the description from dbt, or `"TODO: Add model description"` if missing
- All `.py` files end with a newline (POSIX standard)

#### 5. "OTS compilation failed"

**Problem:** OTS format import failed during compilation.

**Solution:**
1. Check that t4t format import works first:
   ```bash
   t4t import ./my_dbt_project ./imported_project --format t4t
   ```
2. Then compile manually:
   ```bash
   cd imported_project
   t4t compile .
   ```
3. Check for Python model evaluation issues
4. Review OTS compilation errors in the import report

### Getting Help

1. **Check the import report:**
   ```bash
   cat imported_project/IMPORT_REPORT.md
   ```

2. **Review the conversion log:**
   ```bash
   cat imported_project/CONVERSION_LOG.json
   ```

3. **Use verbose mode:**
   ```bash
   t4t import ./my_dbt_project ./imported_project -v
   ```

4. **Run dry-run first:**
   ```bash
   t4t import ./my_dbt_project ./imported_project --dry-run
   ```

## Best Practices

### 1. Validate Before Import

```bash
# Test your dbt project first
cd my_dbt_project
dbt debug
dbt compile
```

### 2. Use Dry-Run

```bash
# Validate without creating files
t4t import ./my_dbt_project ./imported_project --dry-run
```

### 3. Review Import Report

Always review `IMPORT_REPORT.md` after import to:
- Check for warnings
- Review unsupported features
- Understand variable conversions
- See validation results

### 4. Test Incrementally

```bash
# Import a subset first
t4t import ./my_dbt_project ./imported_project \
  --select tag:staging

# Test the imported subset
cd imported_project
t4t test .
```

### 5. Preserve Filenames for Familiarity

If your team is familiar with dbt file names:

```bash
t4t import ./my_dbt_project ./imported_project \
  --preserve-filenames
```

### 6. Use Custom Schema

If your dbt project uses custom schemas:

```bash
t4t import ./my_dbt_project ./imported_project \
  --default-schema analytics
```

## Migration Strategy

### Option 1: Complete Migration

Import everything at once:

```bash
t4t import ./my_dbt_project ./imported_project
cd imported_project
t4t test .
t4t run .
```

### Option 2: Gradual Migration

1. Import with Jinja preserved:
   ```bash
   t4t import ./my_dbt_project ./imported_project --keep-jinja
   ```

2. Convert models incrementally as t4t adds Jinja2 support

3. Test each converted model

### Option 3: Selective Migration

1. Import production models first:
   ```bash
   t4t import ./my_dbt_project ./imported_project \
     --select tag:production
   ```

2. Test and validate

3. Import remaining models

## Limitations

See [dbt Import Limitations](dbt-import-limitations.md) for a complete list of unsupported features and known issues.

### Key Limitations

- **Source Freshness Tests:** Skipped with warnings (not yet supported in t4t)
- **Complex Jinja:** Converted to Python models (may require manual review)
- **Custom Macros:** Some complex macros may not convert automatically
- **Package Dependencies:** ✅ Packages are automatically downloaded and macros are expanded into SQL
- **Dependency Selection:** Basic name/tag selection only (`model+`, `+model` not yet supported)

## Next Steps

After importing:

1. **Review the import report** - Check for warnings and issues
2. **Validate the project** - Run `t4t debug .`
3. **Test the project** - Run `t4t test .`
4. **Run models** - Execute with `t4t run .`
5. **Update configuration** - Adjust `project.toml` if needed
6. **Review Python models** - Check models with complex Jinja

## Related Documentation

- [CLI Reference](cli-reference.md) - Complete command reference
- [dbt Import Limitations](dbt-import-limitations.md) - Unsupported features
- [Getting Started](../getting-started/quick-start.md) - t4t basics
- [Execution Engine](execution-engine.md) - Running models
- [Data Quality Tests](data-quality-tests.md) - Testing in t4t

