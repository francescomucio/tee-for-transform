# dbt Importer

Imports dbt projects into t4t format, converting models, tests, macros, seeds, and configuration.

## Status

**Current Version**: Phase 7 Complete ✅

All 7 phases of the dbt importer are implemented and functional.

## Quick Start

```bash
# Import a dbt project
t4t import ./my_dbt_project ./imported_project

# Import to OTS format
t4t import ./my_dbt_project ./imported_project --format ots

# Dry run to validate
t4t import ./my_dbt_project ./imported_project --dry-run
```

## Features

### ✅ Implemented

- **Model Conversion**: SQL models with Jinja templates
- **Test Conversion**: Standard, generic, and singular tests
- **Macro Conversion**: Macros converted to UDFs where possible
- **Seed Conversion**: CSV, JSON, TSV files copied
- **Configuration**: `dbt_project.yml` → `project.toml`, `profiles.yml` → connection config
- **Schema Resolution**: Follows dbt's priority rules
- **Variable Conversion**: `{{ var('name') }}` → `@name` (automatic)
- **Validation**: Syntax, dependencies, metadata, and optional execution validation
- **Reporting**: Comprehensive `IMPORT_REPORT.md` and `CONVERSION_LOG.json`
- **OTS Format**: Direct import to OTS modules
- **Model Selection**: `--select` and `--exclude` with name patterns and tags
- **Metadata Files**: Always created for all models with `table_name` and TODO description if missing
- **Alias Handling**: Supports aliases from config blocks and `schema.yml` with proper priority

### ⚠️ Partially Implemented

- **Source Metadata**: References converted, metadata logged but not preserved
- **Incremental Strategies**: Basic strategies supported, some missing (see issues)

### ❌ Not Supported

- **Source Freshness Tests**: Skipped with warnings (Issue #1)
- **Custom `generate_schema_name` Macros**: Uses standard dbt logic
- **Package Inlining**: Detection only, no automatic inlining
- **Dependency Resolution**: Basic selection only (`model+`, `+model` not supported - Issue #8)

## Known Limitations

See [dbt Import Limitations](../../../docs/user-guide/dbt-import-limitations.md) for complete details.

### Key Limitations

1. **Source Freshness Tests**: Not yet supported in t4t (Issue #1)
2. **Complex Jinja**: Converted to Python models (may require manual review)
3. **Custom Macros**: Some complex macros may not convert automatically
4. **Package Dependencies**: Detected but not automatically inlined
5. **Dependency Selection**: Basic name/tag selection only (`model+`, `+model` not yet supported)

## Architecture

### Core Components

- **`importer.py`**: Main orchestration function
- **`model_converter.py`**: Converts dbt models to t4t format
- **`jinja_converter.py`**: Handles Jinja template conversion
- **`schema_resolver.py`**: Resolves schema names following dbt's rules
- **`test_converter.py`**: Converts dbt tests to t4t format
- **`macro_converter.py`**: Converts macros to UDFs
- **`report_generator.py`**: Generates import reports

### Import Process

1. **Phase 1**: Project detection and structure creation
2. **Phase 2**: Model conversion and seeds
3. **Phase 3**: Macros, variables, and reporting
4. **Phase 4**: Test conversion
5. **Phase 5**: Configuration and project setup
6. **Phase 6**: Validation
7. **Phase 7**: OTS compilation (if `--format ots`)

## Documentation

- **User Guide**: [dbt Import Guide](../../../docs/user-guide/dbt-import.md)
- **Limitations**: [dbt Import Limitations](../../../docs/user-guide/dbt-import-limitations.md)
- **CLI Reference**: [CLI Reference](../../../docs/user-guide/cli-reference.md#import---import-projects-from-other-formats)

## GitHub Issues

Related issues tracking missing features:

- [#1](https://github.com/francescomucio/tee-for-transform/issues/1) - Freshness Tests Support
- [#2](https://github.com/francescomucio/tee-for-transform/issues/2) - Source Metadata Handling
- [#3](https://github.com/francescomucio/tee-for-transform/issues/3) - Missing Incremental Strategies
- [#4](https://github.com/francescomucio/tee-for-transform/issues/4) - Jinja2 Support
- [#5](https://github.com/francescomucio/tee-for-transform/issues/5) - Spark Support (insert_overwrite)
- [#6](https://github.com/francescomucio/tee-for-transform/issues/6) - on_schema_change Support
- [#8](https://github.com/francescomucio/tee-for-transform/issues/8) - Dependency Resolution (model+, +model)

## Testing

Unit tests are in `tests/importer/dbt/`:
- Model conversion tests
- Jinja conversion tests
- Schema resolution tests
- Test conversion tests
- Macro conversion tests
- Integration tests with jaffle-shop project

Run tests:
```bash
uv run pytest tests/importer/dbt/ -v
```

## Code Coverage

Current coverage:
- `importer.py`: 62%
- `report_generator.py`: 57%
- Other modules: Varies

## Contributing

When adding new features:
1. Update this README
2. Add unit tests
3. Update user documentation
4. Update limitations documentation if needed

