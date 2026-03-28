# dbt Import Limitations

This document lists known limitations, unsupported features, and workarounds for the dbt importer.

## Unsupported Features

### 1. Source Freshness Tests

**Status:** ❌ Not Supported  
**Issue:** [GitHub Issue #1](https://github.com/francescomucio/tee-for-transform/issues/1)

**What:** dbt source freshness tests (defined in `__sources.yml`)

**Behavior:** Freshness tests are detected and skipped during import with a warning logged in the import report.

**Workaround:** 
- Freshness tests are documented in the import report
- You can manually create freshness tests in t4t once support is added
- For now, use regular data quality tests to check data recency

**Example:**
```yaml
# dbt __sources.yml - Skipped
sources:
  - name: my_source
    freshness:
      warn_after: {count: 24, period: hour}
```

### 2. Source Metadata

**Status:** ⚠️ Partially Supported  
**Issue:** [GitHub Issue #2](https://github.com/francescomucio/tee-for-transform/issues/2)

**What:** dbt source metadata (descriptions, tags, etc. in `__sources.yml`)

**Behavior:** 
- Source references (`{{ source('schema', 'table') }}`) are converted to `schema.table`
- Source metadata is logged but not preserved in t4t format

**Workaround:**
- Source metadata is documented in the import report
- You can manually add metadata to t4t models if needed

### 3. Missing Incremental Strategies

**Status:** ⚠️ Partially Supported  
**Issues:** 
- [GitHub Issue #3](https://github.com/francescomucio/tee-for-transform/issues/3) - Generic missing strategies
- [GitHub Issue #5](https://github.com/francescomucio/tee-for-transform/issues/5) - Spark `insert_overwrite`
- [GitHub Issue #6](https://github.com/francescomucio/tee-for-transform/issues/6) - `on_schema_change`

**What:** Some dbt incremental materialization strategies

**Supported Strategies:**
- ✅ `merge` → t4t merge strategy
- ✅ `append` → t4t append strategy
- ✅ `delete+insert` → t4t delete+insert strategy

**Unsupported Strategies:**
- ❌ `insert_overwrite` (Spark) - Falls back to `append` with warning
- ❌ `on_schema_change` - Logged with warning, link to OTS issue

**Behavior:** Unsupported strategies use a fallback strategy (`append`) with warnings logged in the import report.

**Workaround:**
- Check the import report for strategy warnings
- Manually update incremental config in metadata files if needed
- Wait for t4t to add support for missing strategies

### 4. Complex Jinja Templates

**Status:** ⚠️ Partially Supported

**What:** Complex Jinja templates (loops, complex conditionals, unconvertible macros)

**Behavior:**
- Simple Jinja (`ref()`, `source()`, `var()`) is converted automatically
- Complex Jinja is converted to Python models
- Conversion failures are logged with TODOs

**Workaround:**
- Review Python models generated from complex Jinja
- Manually convert or simplify Jinja if needed
- Use `--keep-jinja` to preserve Jinja (requires Jinja2 support in t4t)

**Example:**
```sql
-- Complex Jinja → Python model
{% for table in tables %}
  SELECT * FROM {{ table }}
{% endfor %}
```

### 5. Custom `generate_schema_name` Macros

**Status:** ❌ Not Supported

**What:** Custom `generate_schema_name` macros in dbt

**Behavior:** The importer uses standard dbt schema resolution logic. Custom macros are not executed.

**Workaround:**
- Manually adjust schema names after import
- Update `project.toml` or model metadata files
- Use `--default-schema` to override

### 6. Package Macro/Model Inlining

**Status:** ✅ Supported

**What:** Automatic downloading and macro expansion for dbt package dependencies

**Behavior:**
- Packages are automatically downloaded from `packages.yml` or `dependencies.yml`
- Package macros are loaded and expanded into SQL during model rendering
- Supports packages from:
  - dbt Hub (`package:` syntax)
  - Git repositories (`git:` + `revision:`/`ref:`)
  - Local paths (`local:`)
- Packages are stored in `.packages/` directory
- A `packages.lock` file tracks resolved commit SHAs

**Note:**
- Package models are not automatically inlined (only macros are expanded)
- Complex package macros that use runtime SQL execution may still be converted to Python models

### 7. Dependency Resolution (`model+`, `+model`)

**Status:** ❌ Not Supported  
**Issue:** [GitHub Issue #8](https://github.com/francescomucio/tee-for-transform/issues/8)

**What:** dbt-style dependency selection (`model+`, `+model`)

**Behavior:**
- Basic name/tag-based selection works (`--select model_name`, `--select tag:production`)
- Dependency traversal (`model+`, `+model`) is not supported

**Workaround:**
- Manually select all dependent models
- Use wildcards: `--select staging_*`
- Import all models and use t4t's selection after import

**Example:**
```bash
# Not supported:
t4t import ./dbt_project ./t4t_project --select customers+

# Workaround:
t4t import ./dbt_project ./t4t_project \
  --select customers \
  --select orders \
  --select order_items
```

### 8. Full Jinja2 Support

**Status:** ⚠️ Coming Soon  
**Issue:** [GitHub Issue #4](https://github.com/francescomucio/tee-for-transform/issues/4)

**What:** Full Jinja2 template rendering in t4t

**Behavior:**
- `--keep-jinja` preserves Jinja templates
- Jinja is not rendered during execution (yet)
- Requires Jinja2 support in t4t

**Workaround:**
- Use `--keep-jinja` for gradual migration
- Convert Jinja to Python models
- Wait for Jinja2 support in t4t

## Known Limitations

### 1. Variables with `--keep-jinja`

**Status:** ⚠️ Requires Jinja2 Support

**What:** Variable conversion when using `--keep-jinja` flag

**Behavior:**
- ✅ Variables ARE automatically converted in SQL models (when not using `--keep-jinja`):
  - `{{ var('name') }}` → `@name`
  - `{{ var('name', 'default') }}` → `@name:default`
- ⚠️ When `--keep-jinja` is used, variables are left as Jinja (not converted)
- ✅ Variables work in Python models (injected into namespace)

**Note:** The `--keep-jinja` flag intentionally preserves Jinja templates, including `var()` calls. This requires Jinja2 support in t4t (coming soon).

**Workaround:**
- Don't use `--keep-jinja` if you want variables converted automatically
- Variables are documented in the import report
- For Python models, variables are automatically available in the function namespace

### 2. Model Config Block Schema

**Status:** ⚠️ Partially Supported

**What:** Schema specified in model file config block (`{{ config(schema='...') }}`)

**Behavior:**
- Config blocks are parsed
- Schema from config block is used in resolution
- Some edge cases may not be fully handled

**Workaround:**
- Check schema resolution in import report
- Manually adjust if needed

### 3. Test Severity Levels

**Status:** ⚠️ Basic Support

**What:** dbt test severity levels (`error`, `warn`)

**Behavior:**
- Severity is extracted from test config
- Basic mapping to t4t severity
- Some edge cases may not be fully converted

**Workaround:**
- Review test conversions in import report
- Manually adjust severity if needed

## Workarounds

### For Unsupported Features

1. **Check the Import Report**
   - All unsupported features are documented
   - Warnings indicate what needs attention
   - Conversion log has detailed information

2. **Manual Conversion**
   - Some features can be manually converted after import
   - Review generated Python models
   - Update metadata files as needed

3. **Gradual Migration**
   - Use `--keep-jinja` to preserve templates
   - Convert incrementally as t4t adds support
   - Test each converted component

4. **Selective Import**
   - Import only supported features first
   - Use `--select` and `--exclude` to filter
   - Import remaining features later

## Future Enhancements

The following features are planned but not yet implemented:

- ✅ Source freshness tests (Issue #1)
- ✅ Source metadata preservation (Issue #2)
- ✅ Missing incremental strategies (Issues #3, #5, #6)
- ✅ Full Jinja2 support (Issue #4)
- ✅ Dependency resolution (`model+`, `+model`) (Issue #8)
- ✅ Package inlining
- ✅ Variables auto-conversion
- ✅ Custom macro support

## Getting Help

If you encounter issues not covered here:

1. **Check the Import Report:**
   ```bash
   cat imported_project/IMPORT_REPORT.md
   ```

2. **Review the Conversion Log:**
   ```bash
   cat imported_project/CONVERSION_LOG.json
   ```

3. **Use Verbose Mode:**
   ```bash
   t4t import ./dbt_project ./t4t_project -v
   ```

4. **Create a GitHub Issue:**
   - Include the import report
   - Describe the dbt feature you're trying to import
   - Provide a minimal example if possible

## Related Documentation

- [dbt Import Guide](dbt-import.md) - Complete import guide
- [CLI Reference](cli-reference.md) - Command reference
- [GitHub Issues](https://github.com/francescomucio/tee-for-transform/issues) - Track feature requests

