# CLI Reference

Complete reference for all t4t command-line interface commands and options.

## Overview

t4t provides a comprehensive command-line interface through `t4t`. All commands can be run using `uv run t4t` or directly as `t4t` if installed:

```bash
# Using uv (recommended for development)
uv run t4t <command> [options]

# Direct execution (if installed)
t4t <command> [options]
```

## Common Options

Most commands support these common options:

- `-v, --verbose` - Enable verbose output
- `--vars <JSON>` - Pass variables to models (JSON format)
- `-s, --select <pattern>` - Select models by pattern (can be used multiple times)
- `-e, --exclude <pattern>` - Exclude models by pattern (can be used multiple times)

### Variables Format

Variables are passed as JSON strings:

```bash
--vars '{"env": "prod", "start_value": "2024-01-01"}'
```

### Selection Patterns

Selection patterns support:
- Model names: `--select my_model`
- Wildcards: `--select my_*` or `--select *users*`
- Tags: `--select tag:nightly` or `--select tag:production`
- Multiple patterns: `--select my_model --select tag:analytics`
- Definition state: `--select definition:changed` — models whose definition changed vs. the stored baseline
- Run state: `--select run:failed` — models that failed in the last run (`--retry` is sugar for `--select run:failed+`)
- Graph modifiers: `+my_model` (upstream), `my_model+` (downstream), `+my_model+` (both)
- Intersection (AND): comma, no spaces — `--select "definition:changed,tag:nightly"`

Repeated `--select` flags OR together (union); a comma within one value ANDs
together (intersection) — this matches dbt's own selector-combination
syntax exactly. See the [Model Selection guide](selection.md) for the full
reference, including `definition:changed`/`run:failed`/`--retry` and how
graph modifiers interact with comma groups.

## Commands

### `init` - Initialize a New Project

Create a new t4t project with the proper structure.

**Usage:**
```bash
t4t init <project_name> [--database-type <type>]
```

**Arguments:**
- `project_name` (required) - Name of the project (will create a folder with this name)

**Options:**
- `-d, --database-type <type>` - Database type (default: `duckdb`)
  - Supported: `duckdb`, `snowflake`, `postgresql`, `bigquery`, `motherduck`

**Examples:**
```bash
# Initialize with DuckDB (default)
t4t init my_project

# Initialize with Snowflake
t4t init my_project -d snowflake

# Initialize with PostgreSQL
t4t init my_project -d postgresql

# Initialize with BigQuery
t4t init my_project -d bigquery

# Initialize with MotherDuck
t4t init my_project -d motherduck
```

**What it creates:**
- Project directory with the specified name
- `project.toml` configuration file with database connection template
- Default directories: `models/`, `tests/`, `seeds/`
- `data/` directory (for DuckDB projects only)

**MotherDuck Configuration:**
When using `-d motherduck`, the generated `project.toml` includes:
```toml
project_folder = "my_project"

[environments.dev.connection]
type = "duckdb"
path = "md:my_project"
database = "my_project"
schema = "main"

[environments.dev.connection.extra]
# MotherDuck access token (recommended: use MOTHERDUCK_TOKEN environment variable instead)
# motherduck_token = "your_motherduck_access_token_here"

[flags]
materialization_change_behavior = "warn"
```

**Note:** For MotherDuck authentication, set the `MOTHERDUCK_TOKEN` environment variable (recommended) or uncomment and set `motherduck_token` in the `[environments.dev.connection.extra]` section.

**Generated `project.toml` structure:**
```toml
project_folder = "my_project"

[environments.dev.connection]
# Database-specific connection settings
type = "duckdb"
path = "data/my_project.duckdb"

[flags]
materialization_change_behavior = "warn"  # Options: "warn", "error", "ignore"
```

---

### `import` - Import Projects from Other Formats

Import projects from other transformation tools (currently supports dbt) into t4t format.

**Usage:**
```bash
t4t import <source_project_folder> <target_project_folder> [options]
```

**Arguments:**
- `source_project_folder` (required) - Path to the source project folder (e.g., dbt project)
- `target_project_folder` (required) - Path where the imported t4t project will be created

**Options:**
- `--format <format>` - Output format: `t4t` (default) or `ots`
- `--preserve-filenames` - Keep original file names instead of using final table names
- `--validate-execution` - Run execution validation (requires database connection)
- `-v, --verbose` - Enable verbose output
- `--dry-run` - Show what would be imported without actually importing
- `--keep-jinja` - Keep Jinja2 templates in models (converts `ref()` and `source()` only). Note: Requires Jinja2 support in t4t (coming soon)
- `--default-schema <schema>` - Default schema name for models and functions (default: `public`)
- `--target-dialect <dialect>` - Target database dialect for SQL conversion (e.g., `postgresql`, `snowflake`, `duckdb`). Defaults to PostgreSQL if not specified. Used for macro-to-UDF conversion.
- `-s, --select <pattern>` - Select models to import. Can be used multiple times. Supports name patterns and tags (e.g., `my_model`, `tag:nightly`)
- `-e, --exclude <pattern>` - Exclude models from import. Can be used multiple times. Supports name patterns and tags (e.g., `deprecated`, `tag:test`)

**Examples:**
```bash
# Import dbt project to t4t format
t4t import ./my_dbt_project ./imported_project

# Import to OTS format
t4t import ./my_dbt_project ./imported_project --format ots

# Import with preserved filenames
t4t import ./my_dbt_project ./imported_project --preserve-filenames

# Dry run to validate before importing
t4t import ./my_dbt_project ./imported_project --dry-run

# Import specific models only
t4t import ./my_dbt_project ./imported_project --select customers --select orders

# Import models by tag
t4t import ./my_dbt_project ./imported_project --select tag:production

# Exclude test models
t4t import ./my_dbt_project ./imported_project --exclude tag:test

# Import with custom schema and dialect
t4t import ./my_dbt_project ./imported_project --default-schema analytics --target-dialect snowflake

# Keep Jinja templates (for gradual migration)
t4t import ./my_dbt_project ./imported_project --keep-jinja

# Verbose output
t4t import ./my_dbt_project ./imported_project -v
```

**What it does:**
1. Detects project type (currently supports dbt)
2. Parses source project configuration (`dbt_project.yml`, `profiles.yml`, etc.)
3. Converts models, tests, macros, and seeds to t4t format
4. Generates `project.toml` with connection configuration
5. Creates import reports (`IMPORT_REPORT.md` and `CONVERSION_LOG.json`)
6. Validates imported project (syntax, dependencies, metadata)
7. If `--format ots`, compiles to OTS modules

**Output:**
- Imported project structure:
  - `models/` - Converted SQL/Python models
  - `tests/` - Converted data quality tests
  - `functions/` - Converted macros as UDFs
  - `seeds/` - Copied seed files
  - `project.toml` - Project configuration
  - `IMPORT_REPORT.md` - Comprehensive import report
  - `CONVERSION_LOG.json` - Detailed conversion log
  - `output/ots_modules/` - OTS modules (if `--format ots`)

**Import Report:**
The import process generates a comprehensive report (`IMPORT_REPORT.md`) that includes:
- Summary statistics (models, tests, macros converted)
- Validation results
- OTS compilation results (if applicable)
- Model conversion details
- Variables documentation
- Test conversion details
- Macro conversion details
- Warnings and unsupported features
- Package dependencies

**Selection Patterns:**
- Model names: `--select customers` or `--select my_model`
- Wildcards: `--select staging_*` or `--select *users*`
- Tags: `--select tag:production` or `--select tag:nightly`
- Multiple patterns: `--select customers --select tag:analytics`
- Exclusion: `--exclude deprecated --exclude tag:test`

**Notes:**
- The target folder must not exist (unless using `--dry-run`)
- dbt `profiles.yml` is automatically detected from standard locations (`~/.dbt/` or `DBT_PROFILES_DIR`)
- Connection configuration is extracted from `profiles.yml` and added to `project.toml`
- Source freshness tests are skipped with warnings (not yet supported in t4t)
- Complex Jinja templates are converted to Python models when automatic conversion fails
- See [dbt Import Guide](dbt-import.md) for detailed migration instructions

---

### `run` - Execute SQL Models

Parse and execute SQL models in dependency order.

**Usage:**
```bash
t4t run <project_folder> [options]
```

**Arguments:**
- `project_folder` (required) - Path to the project folder containing `project.toml`

**Options:**
- `-v, --verbose` - Enable verbose output
- `--vars <JSON>` - Variables to pass to models (JSON format)
- `-s, --select <pattern>` - Select models by pattern (can be used multiple times) — see [Model Selection](selection.md) for the full syntax (`definition:changed`, `run:failed`, graph modifiers, AND/OR combining)
- `-e, --exclude <pattern>` - Exclude models by pattern (can be used multiple times)
- `--retry` - Re-run models that failed or were skipped downstream in the last run; sugar for `--select run:failed+`. Cannot be combined with `--select`.
- `--auto-resolve-level-conflicts` - When generating lookups, resolve duplicate hierarchy level names as `<dimension>_<level>` (default: on)

**Examples:**
```bash
# Run all models
t4t run ./my_project

# Run with variables
t4t run ./my_project --vars '{"env": "prod", "start_value": "2024-01-01"}'

# Run specific models
t4t run ./my_project --select my_model

# Run models with specific tag
t4t run ./my_project --select tag:nightly

# Exclude test models
t4t run ./my_project --exclude tag:test

# Combine selection and exclusion
t4t run ./my_project --select my_model --exclude tag:deprecated

# Run only models whose definition changed, plus their downstream dependents
t4t run ./my_project --select definition:changed+

# Retry only what failed (or was skipped downstream) last run
t4t run ./my_project --retry
```

**What it does:**
1. Compiles project to OTS modules (parses SQL/Python models and functions, loads imported OTS modules)
2. Loads compiled OTS modules from `output/ots_modules/`
3. Executes functions before models (functions must be created before models that depend on them)
4. Resolves dependencies automatically
5. Executes models in the correct order
6. Materializes results as tables/views in the database

**Output:**
The run command provides detailed output including:
- Function execution status (functions are executed before models)
- Model execution status with row counts
- Final summary with counts of executed tables and functions

**Note:** The `run` command does NOT execute tests. Use `t4t test` to run tests separately, or `t4t build` to execute models with interleaved test execution.

**Empty Projects:**
If your project has no models, the `run` command will compile successfully and return with a message indicating 0 models were executed. This allows you to initialize projects and validate configuration before adding models.

---


### `build` - Build Models with Tests

Build models with interleaved test execution, stopping on the first ERROR severity test failure.

**Usage:**
```bash
t4t build <project_folder> [options]
```

**Arguments:**
- `project_folder` (required) - Path to the project folder containing `project.toml`

**Options:**
- `-v, --verbose` - Enable verbose output
- `--vars <JSON>` - Variables to pass to models (JSON format)
- `-s, --select <pattern>` - Select models by pattern (can be used multiple times) — see [Model Selection](selection.md) for the full syntax (`definition:changed`, `run:failed`, graph modifiers, AND/OR combining)
- `-e, --exclude <pattern>` - Exclude models by pattern (can be used multiple times)
- `--retry` - Re-run models that failed or were skipped downstream in the last run; sugar for `--select run:failed+`. Cannot be combined with `--select`.
- `--auto-resolve-level-conflicts` - When generating lookups, resolve duplicate hierarchy level names as `<dimension>_<level>` (default: on)

**Examples:**
```bash
# Build all models with tests
t4t build ./my_project

# Build with variables
t4t build ./my_project --vars '{"env": "prod"}'

# Build specific models
t4t build ./my_project --select my_model

# Retry only what failed last build
t4t build ./my_project --retry
```

**What it does:**
1. Compiles project to OTS modules (parses SQL/Python models and functions, loads imported OTS modules)
2. Loads compiled OTS modules from `output/ots_modules/`
3. Executes functions before models (functions must be created before models that depend on them)
4. Executes models in dependency order with interleaved test execution
5. Runs tests immediately after each model/function execution
6. Automatically loads seeds before execution
7. Stops on the first ERROR severity test failure

**Output:**
The build command provides detailed output including:
- Function execution status (functions are executed before models)
- Model execution status with row counts
- Test execution results for each model/function
- Final summary with counts of executed tables, functions, and tests

**Exit codes:**
- `0` - All models, functions, and tests passed
- `1` - Model/function execution failed or ERROR severity test failed

---

### `test` - Run Data Quality Tests

Execute data quality tests on models independently.

**Usage:**
```bash
t4t test <project_folder> [options]
```

**Arguments:**
- `project_folder` (required) - Path to the project folder containing `project.toml`

**Options:**
- `-v, --verbose` - Enable verbose output (shows detailed test results)
- `--vars <JSON>` - Variables to pass to models (JSON format)
- `-s, --select <pattern>` - Select models by pattern (can be used multiple times)
- `-e, --exclude <pattern>` - Exclude models by pattern (can be used multiple times)

**Examples:**
```bash
# Run all tests
t4t test ./my_project

# Run tests with variables
t4t test ./my_project --vars '{"env": "prod"}'

# Test specific models
t4t test ./my_project --select my_schema.*

# Verbose output
t4t test ./my_project -v
```

**What it does:**
1. Compiles project to OTS modules (parses SQL/Python models, loads imported OTS modules)
2. Loads compiled OTS modules from `output/ots_modules/`
3. Builds dependency graph
4. Runs all data quality tests

**Exit codes:**
- `0` - All tests passed
- `1` - One or more ERROR severity tests failed

---

### `seed` - Load Seed Files

Load seed files (CSV, JSON, TSV) into database tables.

**Usage:**
```bash
t4t seed <project_folder> [options]
```

**Arguments:**
- `project_folder` (required) - Path to the project folder containing `project.toml`

**Options:**
- `-v, --verbose` - Enable verbose output
- `--vars <JSON>` - Variables to pass to models (JSON format)

**Examples:**
```bash
# Load all seeds
t4t seed ./my_project

# Load seeds with verbose output
t4t seed ./my_project -v
```

**What it does:**
1. Discovers seed files in the `seeds/` directory
2. Supports CSV, TSV, and JSON formats
3. Organizes seeds by schema using subdirectories
4. Loads seeds into database tables
5. Reports loading results and row counts

**Seed file organization:**
```
seeds/
├── users.csv                    # → users table
├── orders.csv                   # → orders table
└── my_schema/
    ├── products.json            # → my_schema.products table
    └── customers.tsv            # → my_schema.customers table
```

**Note:** The `build` command automatically loads seeds before execution. Use `seed` when you want to load seeds independently.

**Empty Projects:**
If your project has no models, the `build` command will compile successfully and return with a message indicating 0 models were built. This allows you to initialize projects and validate configuration before adding models.

**Error Handling:**
The build command provides specific error messages for compilation failures (`CompilationError`) and parsing errors (`ParserError`), making it easier to diagnose issues.

---

### `debug` - Test Database Connectivity

Test database connectivity and configuration.

**Usage:**
```bash
t4t debug <project_folder> [options]
```

**Arguments:**
- `project_folder` (required) - Path to the project folder containing `project.toml`

**Options:**
- `-v, --verbose` - Enable verbose output
- `--vars <JSON>` - Variables to pass to models (JSON format)

**Examples:**
```bash
# Test database connection
t4t debug ./my_project

# Test with verbose output
t4t debug ./my_project -v
```

**What it does:**
1. Tests database connection
2. Displays database information (type, version, host, etc.)
3. Lists supported materializations
4. Validates configuration

**Output includes:**
- Connection status
- Database type and version
- Connection details (host, database, warehouse, role, etc.)
- Supported materialization strategies

---

### `generate-lookups` - Generate Lookup Models

Generate lookup table models (`lkp_<level>.sql` / `.py`) from hierarchical dimension metadata. Existing lookup files are skipped.

**Usage:**
```bash
t4t generate-lookups <project_folder> [options]
```

**Arguments:**
- `project_folder` (required) - Path to the project folder containing `project.toml`

**Options:**
- `-v, --verbose` - Enable verbose output
- `--vars <JSON>` - Variables to pass to models (JSON format)
- `--auto-resolve-level-conflicts` - Resolve duplicate hierarchy level names as `<dimension>_<level>` (default: on)

**Examples:**
```bash
t4t generate-lookups ./my_project
t4t generate-lookups ./my_project --vars '{"env": "prod"}'
```

**Note:** `t4t run`, `t4t build`, and `t4t docs` refresh generated lookups by default (unless you use `--skip-lookups` on `docs`). Use `generate-lookups` when you only want to materialize lookup SQL/Python files on disk without a full run.

---

### `compile` - Compile Project to OTS Modules

Compile t4t project to Open Transformation Specification (OTS) modules and test libraries.

**Usage:**
```bash
t4t compile <project_folder> [options]
```

**Arguments:**
- `project_folder` (required) - Path to the project folder containing `project.toml`

**Options:**
- `-v, --verbose` - Enable verbose output
- `--vars <JSON>` - Variables to pass to models (JSON format)
- `-f, --format <format>` - Output format: `json` or `yaml` (default: `json`)

**Examples:**
```bash
# Compile to JSON (default)
t4t compile ./my_project

# Compile to YAML
t4t compile ./my_project --format yaml

# Compile with variables
t4t compile ./my_project --vars '{"env": "prod"}'
```

**What it does:**
1. Parses all SQL/Python models in the `models/` directory
2. Discovers and validates imported OTS modules in `models/`
3. Detects conflicts (duplicate `transformation_id`)
4. Merges all models (SQL, Python, and imported OTS)
5. Converts to OTS format
6. Validates compiled modules
7. Exports OTS modules to `output/ots_modules/`
8. Exports merged test library to `output/ots_modules/`

**Output:**
- OTS modules: `{database}__{schema}.ots.json` (or `.ots.yaml`)
- Test library: `{project_name}_test_library.ots.json` (or `.ots.yaml`)

**Note:** The `run`, `build`, and `test` commands automatically compile before execution. Use `compile` when you want to generate OTS modules and analysis files without executing.

---

### `docs` - Generate Documentation Site

Generate an interactive static HTML documentation site with dependency graph visualization, similar to dbt docs.

**Usage:**
```bash
t4t docs <project_folder> [options]
```

**Arguments:**
- `project_folder` (required) - Path to the project folder containing `project.toml`

**Options:**
- `-v, --verbose` - Enable verbose output
- `--vars <JSON>` - Variables to pass to models (JSON format)
- `-o, --output-dir <path>` - Output directory for docs (default: `output/docs`)
- `--auto-resolve-level-conflicts` - When generating lookups before docs, resolve duplicate hierarchy level names as `<dimension>_<level>` (default: on)
- `--skip-lookups` - Skip lookup generation before building docs
- `--infer-dim-from-column-names` - Infer dimensional links from fact column names that match dimension/lookup primary keys (default: off)

**Examples:**
```bash
# Generate docs in default location (output/docs)
t4t docs ./my_project

# Generate docs in custom location
t4t docs ./my_project --output-dir ./documentation

# Generate docs with variables
t4t docs ./my_project --vars '{"env": "prod"}'

# Generate docs without refreshing generated lookups
t4t docs ./my_project --skip-lookups

# Infer dimensional graph edges from fact column naming
t4t docs ./my_project --infer-dim-from-column-names
```

**What it does:**
1. Optionally refreshes generated lookups (unless `--skip-lookups` is used)
2. Discovers and parses functions (UDFs)
3. Builds dependency graph showing relationships between models, functions, and tests
4. Generates static HTML documentation site with:
   - Interactive dependency graph visualization
   - Sidebar navigation tree
   - Model detail pages with SQL code (original and compiled)
   - Clickable dependencies and dependents
   - Test information
   - Schema definitions

**Output:**
- Static HTML files in `output/docs/` (or custom output directory)
- `index.html` - Main interactive documentation page
- `model_*.html` - Individual model detail pages
- `graph_data.json` - Graph data for interactive features

**Features:**
- **Interactive Graph**: Click nodes to filter, double-click to navigate to detail pages
- **Sidebar Navigation**: Collapsible tree view organized by schema
- **Filtering**: Filter by model name, schema, or type using dbt-style patterns
- **Legend Toggle**: Show/hide different object types (tables, views, functions, tests)
- **Highlighting**: Selected nodes and their dependencies/dependents are highlighted
- **Responsive Design**: Works on different screen sizes

**Opening the Documentation:**
```bash
# After generation, open in browser
open output/docs/index.html  # macOS
xdg-open output/docs/index.html  # Linux
start output/docs/index.html  # Windows
```

**Note:** The documentation site is completely static and can be served from any web server or opened directly in a browser. No server-side processing is required.

---

### `ots` - OTS Module Commands

Commands for working with Open Transformation Specification (OTS) modules.

#### `ots run` - Execute OTS Modules

Execute OTS modules directly without compilation.

**Usage:**
```bash
t4t ots run <ots_path> [options]
```

**Arguments:**
- `ots_path` (required) - Path to OTS module file (`.ots.json`, `.ots.yaml`, `.ots.yml`) or directory containing OTS modules

**Options:**
- `--project-folder <path>` - Optional project folder for connection config and merging with existing models
- `-v, --verbose` - Enable verbose output
- `--vars <JSON>` - Variables to pass to models (JSON format)
- `-s, --select <pattern>` - Select models by pattern (can be used multiple times)
- `-e, --exclude <pattern>` - Exclude models by pattern (can be used multiple times)

**Examples:**
```bash
# Execute a single OTS module
t4t ots run ./output/ots_modules/my_db__schema1.ots.json

# Execute all OTS modules in a directory
t4t ots run ./output/ots_modules/

# Execute with project folder (merges with existing models)
t4t ots run ./external_modules/ --project-folder ./my_project

# Execute with variables
t4t ots run ./modules/ --vars '{"env": "prod"}'
```

**What it does:**
1. Loads OTS modules from the specified path
2. Optionally merges with existing models from project folder
3. Builds dependency graph
4. Executes transformations in dependency order

---

#### `ots validate` - Validate OTS Modules

Validate OTS module files for compliance with the OTS specification.

**Usage:**
```bash
t4t ots validate <ots_path> [options]
```

**Arguments:**
- `ots_path` (required) - Path to OTS module file (`.ots.json`, `.ots.yaml`, `.ots.yml`) or directory containing OTS modules

**Options:**
- `-v, --verbose` - Enable verbose output

**Examples:**
```bash
# Validate a single OTS module
t4t ots validate ./output/ots_modules/my_db__schema1.ots.json

# Validate all OTS modules in a directory
t4t ots validate ./output/ots_modules/

# Validate with verbose output
t4t ots validate ./module.ots.yaml -v
```

**What it validates:**
- OTS version compatibility (supports 0.1.0 and below)
- Schema location matches file path
- Required fields and structure
- Module format (JSON/YAML)

---

### `help` - Show Help Information

Display help information for the CLI. This command shows the same output as `t4t --help`.

**Usage:**
```bash
t4t help              # Equivalent to 't4t --help'
t4t --help            # Show general help (same as 't4t help')
t4t <command> --help  # Show command-specific help
```

**Examples:**
```bash
# Show general help (both commands are equivalent)
t4t help
t4t --help

# Show help for specific command
t4t init --help
t4t run --help
t4t compile --help
t4t generate-lookups --help
t4t ots --help
t4t ots run --help
```

---

## Command Comparison

| Command | Compiles | Executes Models | Runs Tests | Loads Seeds | Stops on Test Failure |
|---------|----------|----------------|------------|-------------|----------------------|
| `compile` | ✅ | ❌ | ❌ | ❌ | N/A |
| `run` | ✅ | ✅ | ❌ | ❌ | N/A |
| `build` | ✅ | ✅ | ✅ (interleaved) | ✅ | ✅ |
| `test` | ✅ | ❌ | ✅ | ❌ | ✅ (ERROR only) |
| `seed` | ❌ | ❌ | ❌ | ✅ | N/A |
| `debug` | ❌ | ❌ | ❌ | ❌ | N/A |
| `generate-lookups` | ❌ | ❌ | ❌ | ❌ | N/A |
| `import` | ❌ | ❌ | ❌ | ❌ | N/A |
| `ots run` | ❌ | ✅ | ❌ | ❌ | ❌ |
| `ots validate` | ❌ | ❌ | ❌ | ❌ | N/A |

## Exit Codes

- `0` - Success
- `1` - Error (command failed, test failure, etc.)
- `130` - Interrupted by user (Ctrl+C)

## Getting Help

For more information:

- Run `t4t --help` for general help
- Run `t4t <command> --help` for command-specific help
- See [Quick Start Guide](../getting-started/quickstart.md) for examples
- See [Examples](examples/README.md) for practical usage patterns
