# Tee for Transform

<img src="https://upload.wikimedia.org/wikipedia/commons/f/f7/Rpb_clothing_icon.svg" alt="Tee Logo" width="80" height="80" align="left" style="margin-right: 15px; margin-bottom: 10px;">

**This is a "what if" project**: What if a transformation tool supported functions? What if it allowed for richer metadata? What if data modeling was a priority? After a chat with a friend, I decided to see how far I could go...

A Python framework for managing SQL data transformations with support for multiple database backends, automatic SQL dialect conversion, and rich metadata-driven modeling. Named "Tee for Transform" (abbreviated as **t4t**), but also because everyone loves a good t-shirt! 👕

## 🚀 Quick Start

Since this is an initial release, there's no pip package available yet. Clone this repository, install with [uv](https://github.com/astral-sh/uv), then scaffold a project with the CLI:

```bash
# Clone the repository
git clone https://github.com/francescomucio/tee-as-transformation
cd tee-as-transformation

# Install the package and dependencies (makes `t4t` available via `uv run`)
uv sync

# Create a new project (DuckDB by default: data/<name>.duckdb, models/, seeds/, tests/)
uv run t4t init my_project

# Optional: pick another backend
# uv run t4t init my_project -d postgresql
# uv run t4t init my_project -d snowflake
# uv run t4t init my_project -d bigquery
# uv run t4t init my_project -d motherduck

# Add a model
echo "SELECT 1 AS id, 'hello' AS message" > my_project/models/my_first_model.sql

# Confirm config and connectivity (edit my_project/project.toml first if not using defaults)
uv run t4t debug my_project

# Run models
uv run t4t run my_project
```

**Coming from dbt?** You can generate a t4t layout from an existing project with `uv run t4t import <path-to-dbt-project> <path-to-new-t4t-project>` (see `t4t import --help`).

**Prefer a hand-written `project.toml`?** Create a folder, add `project.toml`, `models/`, and the rest yourself—the layout matches what `t4t init` produces.

## ✨ Key Features

- **Multi-Database Support**: DuckDB, Snowflake, PostgreSQL, and more
- **User-Defined Functions (UDFs)**: Create reusable SQL and Python functions
- **Dependency-Aware Execution**: Automatic model and function dependency resolution
- **Incremental Materialization**: Efficient data processing with append, merge, and delete+insert strategies
- **Rich Metadata Support**: Python-based metadata configuration with full type safety
- **Dimensional shorthand**: Fact columns can use `dimension` metadata (`date`, `date.month`, …); a logical-name registry is **derived automatically** from dimension models (`table_type` `dim` / `dimension`, or `dim_*` table names) and optional hierarchy level names—no separate config file
- **Comprehensive Tagging**: dbt-style tags and database object tags for tables, views, and schemas
- **Pluggable Architecture**: Easy to add new database adapters
- **Configuration Management**: Flexible configuration via `project.toml`

## 📦 Installation

**Note**: This is an initial release with no pip package available. You must clone this repository to use t4t.

```bash
# Clone the repository
git clone https://github.com/francescomucio/tee-as-transformation
cd tee-as-transformation

# Install dependencies using uv
uv sync

# Install the package in development mode to make t4t available
uv pip install -e .

# Or install specific dependencies
uv add duckdb  # For DuckDB support
uv add snowflake-connector-python  # For Snowflake support
uv add psycopg2-binary  # For PostgreSQL support
```

## 🛠️ CLI Commands

t4t provides a comprehensive command-line interface through `t4t`. All commands can be run using `uv run t4t`:

### Initialize Project
Create a new t4t project with the proper structure:

```bash
# Initialize a new project with DuckDB (default)
uv run t4t init my_project

# Initialize with a specific database type
uv run t4t init my_project -d snowflake
uv run t4t init my_project -d postgresql
uv run t4t init my_project -d bigquery
uv run t4t init my_project -d motherduck
```

The `init` command creates:
- Project directory with the specified name
- `project.toml` configuration file with database connection template and default flags
- Default directories: `models/`, `tests/`, `seeds/`
- `data/` directory (for DuckDB projects only)

**Generated `project.toml` structure (DuckDB example):**
```toml
project_folder = "my_project"

[connection]
type = "duckdb"
path = "data/my_project.duckdb"

[flags]
materialization_change_behavior = "warn"  # Options: "warn", "error", "ignore"
```

Other backends get placeholder connection keys (Snowflake host/user/warehouse, PostgreSQL host/database, BigQuery project/dataset, MotherDuck `md:` path plus optional `[connection.extra]`). Edit these to match your environment.

After initialization, edit `project.toml` to configure your database connection. For Snowflake, PostgreSQL, and BigQuery, you'll need to update the connection parameters with your actual credentials.

### Run Models
Execute SQL models in your project:

```bash
# Run all models in a project
uv run t4t run ./my_project

# Run with variables (JSON format)
# Note: CLI variables map to SQL placeholders (e.g. @start_date), not to config keys like start_value
uv run t4t run ./my_project --vars '{"env": "prod", "start_date": "2024-01-01"}'
```

### Compile Models
Compile and analyze SQL models without execution:

```bash
# Compile models and show dependency analysis
uv run t4t compile ./my_project

# Compile with variables (JSON format)
uv run t4t compile ./my_project --vars '{"env": "dev"}'
```

### Debug Connection
Test database connectivity and configuration:

```bash
# Test database connection
uv run t4t debug ./my_project
```

### Build Models with Tests
Build models and run tests interleaved, stopping on the first ERROR severity test failure:

```bash
# Build models with tests (stops on test failure)
uv run t4t build ./my_project

# Build with variables
uv run t4t build ./my_project --vars '{"env": "prod"}'

# Build specific models
uv run t4t build ./my_project --select my_model
```

The `build` command executes models and their tests in dependency order. If a model fails or an ERROR severity test fails, the build stops and dependent models are skipped. WARNING severity test failures do not stop the build.

### Run Tests
Execute data quality tests on models independently:

```bash
# Run all tests defined in model metadata
uv run t4t test ./my_project

# Run tests with variables (JSON format)
uv run t4t test ./my_project --vars '{"env": "prod"}'

# Override test severity (make specific tests warnings instead of errors)
uv run t4t test ./my_project --severity not_null=warning

# Override severity for specific table/column/test
uv run t4t test ./my_project --severity my_table.id.unique=warning

# Multiple severity overrides
uv run t4t test ./my_project --severity not_null=warning --severity unique=error
```

Tests are automatically executed after model runs with `t4t run`, but you can also run them independently using the `test` command. See [Data Quality Tests](docs/user-guide/data-quality-tests.md) for more information.

### Help
Show help information:

```bash
# Show general help
uv run t4t help

# Show help for specific command
uv run t4t init --help
uv run t4t run --help
uv run t4t build --help
uv run t4t compile --help
uv run t4t debug --help
uv run t4t test --help
uv run t4t seed --help
uv run t4t import --help
uv run t4t docs --help

# Full command list (includes OTS subcommands)
uv run t4t --help
```

## 📚 Documentation

**📖 [Full Documentation](docs/README.md)** - Complete guides, API reference, and examples

### Quick Links
- [Installation](docs/getting-started/installation.md)
- [Quick Start Guide](docs/getting-started/quick-start.md)
- [Configuration](docs/getting-started/configuration.md)
- [Incremental Materialization](docs/user-guide/incremental-materialization.md)
- [Database Adapters](docs/user-guide/database-adapters.md)
- [Data Quality Tests](docs/user-guide/data-quality-tests.md)
- [Examples](docs/user-guide/examples/)

## 🛠️ Development

### Building Documentation

```bash
# Install documentation dependencies
uv add --dev mkdocs mkdocs-material

# Build documentation
uv run python docs/build_docs.py build

# Serve documentation locally
uv run python docs/build_docs.py serve
```

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with verbose output
uv run pytest tests/ -v

# Run specific test patterns
uv run pytest tests/ -k test_name
```

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](docs/development/contributing.md) for details.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🔗 Links

- [Documentation](docs/README.md)
- [GitHub Repository](https://github.com/francescomucio/tee-as-transformation)
- [Examples](docs/user-guide/examples/)