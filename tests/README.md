# Tee Test Suite

This directory contains comprehensive tests for the Tee framework, covering incremental materialization, parsing, testing framework, and database adapters.

## Test Structure

```
tests/
├── conftest.py                           # Shared fixtures and configuration
├── run_incremental_tests.py              # Test runner script
├── README.md                             # This file
├── engine/                               # Core engine tests
│   ├── incremental/                     # Incremental executor tests (split by functionality)
│   │   ├── test_executor_base.py        # Base class and fixtures
│   │   ├── test_should_run.py           # should_run_incremental tests
│   │   ├── test_time_filter.py          # Time filter condition tests
│   │   ├── test_lookback.py             # Lookback parsing and application
│   │   ├── test_variables.py            # Variable resolution tests
│   │   ├── test_date_casting.py         # Date casting tests
│   │   ├── test_strategy.py             # Strategy execution tests
│   │   └── test_integration.py          # Integration tests
│   └── test_incremental_adapter_interface.py  # Adapter interface tests
├── adapters/                             # Database adapter tests
│   ├── fixtures/                        # Test fixtures
│   │   └── metadata_fixtures.py        # Metadata test fixtures
│   ├── duckdb/                          # DuckDB-specific tests
│   │   ├── test_incremental.py         # Functional incremental tests
│   │   └── test_incremental_performance.py  # Performance tests (marked slow)
│   ├── test_metadata_propagation.py    # Metadata propagation tests
│   ├── test_snowflake_tags.py          # Snowflake tag tests
│   └── test_snowflake_schema_tags.py   # Snowflake schema tag tests
├── parser/                               # Parser tests
│   ├── core/                             # Core parser tests
│   │   └── test_project_parser.py
│   ├── parsers/                          # Parser implementation tests
│   │   └── test_python_variable_support.py
│   ├── processing/                      # Processing tests
│   │   └── test_sql_variable_substitution.py
│   ├── output/                           # Output transformation tests
│   │   └── test_ots_tags.py             # OTS tag extraction tests
│   └── shared/                          # Shared utilities tests
│       └── test_metadata_schema.py
├── testing/                              # Testing framework tests
│   ├── standard_tests/                  # Standard test implementations (split by type)
│   │   ├── test_not_null.py            # NotNullTest tests
│   │   ├── test_unique.py               # UniqueTest tests
│   │   ├── test_accepted_values.py      # AcceptedValuesTest tests
│   │   ├── test_relationships.py       # RelationshipsTest tests
│   │   ├── test_no_duplicates.py       # NoDuplicatesTest tests
│   │   └── test_row_count_gt_0.py      # RowCountGreaterThanZeroTest tests
│   ├── test_base.py                      # Base test classes
│   ├── test_executor.py                  # Test executor
│   ├── test_query_generation.py          # Query generation
│   ├── test_sql_test.py                  # SQL test support
│   └── test_test_discovery.py           # Test discovery
├── cli/                                  # CLI tests
│   └── test_selection.py                 # Model selection tests
└── typing/                               # Type system tests
```

## Test Categories

### 1. Engine Tests (`engine/`)

Tests the core incremental logic independently of database implementations:

- **`engine/incremental/`**: Incremental executor tests split by functionality
  - `test_executor_base.py`: Base test class and shared fixtures
  - `test_should_run.py`: Tests for determining when to run incremental vs full load
  - `test_time_filter.py`: Tests for time-based filtering conditions
  - `test_lookback.py`: Tests for lookback parsing and application
  - `test_variables.py`: Tests for variable resolution (`@variable` and `{{ variable }}`)
  - `test_date_casting.py`: Tests for date casting in SQL conditions
  - `test_strategy.py`: Tests for append, merge, and delete+insert strategy execution
  - `test_integration.py`: Integration tests for complete workflows
- **Strategy Logic**: Tests for append, merge, and delete+insert strategies
- **Time Filtering**: Tests for time-based filtering and lookback logic
- **Variable Resolution**: Tests for CLI variable resolution (`@variable` and `{{ variable }}`)
- **State Management**: Tests for incremental state tracking
- **Error Handling**: Tests for error conditions and fallbacks

### 2. Adapter Interface Tests (`test_incremental_adapter_interface.py`)

Tests that verify adapters correctly implement the incremental interface:

- **Interface Compliance**: Tests that adapters implement required methods
- **Behavior Patterns**: Tests for expected adapter behavior
- **Error Handling**: Tests for adapter error handling
- **Fallback Behavior**: Tests for fallback when incremental methods aren't available
- **Data Types**: Tests for proper parameter type handling
- **Performance**: Tests for performance characteristics

### 3. Parser Tests (`parser/`)

Tests for the SQL model parsing system:

- **Project Parsing**: Tests for project-wide model discovery and parsing
- **Python Variable Support**: Tests for Python metadata files with variable substitution
- **SQL Variable Substitution**: Tests for SQL variable replacement (`{{ variable }}`)
- **Metadata Schema**: Tests for metadata schema validation and type checking

### 4. Testing Framework Tests (`testing/`)

Tests for the data quality testing framework itself:

- **Base Classes**: Tests for `TestResult`, `TestSeverity`, `StandardTest`, `TestRegistry`
- **Test Executor**: Tests for test execution and result collection
- **Query Generation**: Tests for database-specific SQL query generation
- **SQL Tests**: Tests for custom SQL test support (dbt-style)
- **Standard Tests** (`testing/standard_tests/`): Tests for built-in test implementations
  - `test_not_null.py`: NotNullTest tests
  - `test_unique.py`: UniqueTest tests
  - `test_accepted_values.py`: AcceptedValuesTest tests
  - `test_relationships.py`: RelationshipsTest tests
  - `test_no_duplicates.py`: NoDuplicatesTest tests
  - `test_row_count_gt_0.py`: RowCountGreaterThanZeroTest tests
- **Test Discovery**: Tests for automatic test discovery from SQL files

### 5. Database-Specific Tests (`adapters/`)

Tests specific to database adapter implementations:

- **Fixtures** (`adapters/fixtures/`): Shared test fixtures
  - `metadata_fixtures.py`: Metadata test data and helper functions
- **DuckDB** (`adapters/duckdb/`): DuckDB-specific tests
  - `test_incremental.py`: Functional incremental materialization tests
  - `test_incremental_performance.py`: Performance tests with large datasets (marked `@pytest.mark.slow`)
- **Snowflake**: Snowflake-specific tests
  - `test_snowflake_tags.py`: Tag attachment tests
  - `test_snowflake_schema_tags.py`: Schema-level tag tests
- **Metadata Propagation**: Tests for metadata propagation across adapters
- **SQL Generation**: Tests for database-specific SQL generation
- **Data Operations**: Tests for actual data operations
- **Schema Handling**: Tests for schema qualification and table creation
- **Performance**: Tests for performance with large datasets
- **Error Scenarios**: Tests for database-specific error conditions

## Running Tests

### Prerequisites

- Run commands from the **package root** (`tee-for-transform/`, next to `pyproject.toml`), not from a subfolder, so `testpaths = ["tests"]` and imports resolve as in CI.
- Install dev dependencies: **`uv sync`** (includes pytest and pytest-cov).

### Choosing what to run: with or without Snowflake E2E

Some tests are tagged **`snowflake_e2e`**. They open a **live Snowflake** session (warehouse, network) and exercise end-to-end materialization and related flows. They are defined under `tests/adapters/snowflake/*_e2e.py` and in `tests/engine/integration/test_function_execution_snowflake.py` (see [Test Markers](#test-markers)).

**Run without Snowflake E2E** (recommended default for local work):

- Typical wall time is **tens of seconds** for the rest of the suite (without coverage); the Snowflake E2E portion alone is often **many minutes**.
- Use this for everyday development, refactors, parser/engine/DuckDB work, and any change that does not need a real Snowflake warehouse to validate.
- Works **without** Snowflake credentials; nothing in that subset requires `tests/.snowflake_config.json`.

```bash
uv run pytest tests/ -m "not snowflake_e2e"
```

Add `-v` for verbose output.

**Coverage (default):** `[tool.pytest.ini_options] addopts` in `pyproject.toml` turns on **`--cov=tee`** and HTML output under **`htmlcov/`**. For a **faster** feedback loop, pass **`--no-cov`** (especially with the full suite).

**Combining markers:** For the **leanest** local run (no Snowflake E2E and no tests marked `slow`), use:

```bash
uv run pytest tests/ -m "not snowflake_e2e and not slow" --no-cov
```

**Run the full suite including Snowflake E2E** when:

- You changed **Snowflake adapter** code, Snowflake-specific SQL, or behavior covered only by those E2E tests.
- You are doing a **final check before merge** or release and have credentials available.
- Your **CI** job is allowed to use Snowflake secrets (often a dedicated workflow or branch).

```bash
uv run pytest tests/
```

Requires Snowflake configuration: use `tests/.snowflake_config.json` (gitignored) or environment variables such as `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, and `SNOWFLAKE_PASSWORD` (see the Snowflake E2E modules under `tests/adapters/snowflake/` for details).

**Run only Snowflake E2E** when you are **debugging Snowflake-specific** failures or iterating on those modules:

```bash
uv run pytest tests/ -m snowflake_e2e -v
```

### Using the Test Runner (`run_incremental_tests.py`)

The script **`tests/run_incremental_tests.py`** is an **optional** helper that runs **pytest on a subset** of the tree (mostly incremental engine, adapter interface, DuckDB, performance). It does **not** replace **`uv run pytest tests/`** for full coverage of the project. Use it when you are focused on incremental materialization code paths; use full pytest for CLI, parser, importer, and the rest.

```bash
# Run all incremental tests
uv run python tests/run_incremental_tests.py all

# Run unit tests only
uv run python tests/run_incremental_tests.py unit

# Run adapter interface tests
uv run python tests/run_incremental_tests.py adapter

# Run DuckDB integration tests
uv run python tests/run_incremental_tests.py duckdb

# Run performance tests
uv run python tests/run_incremental_tests.py performance

# Run with coverage
uv run python tests/run_incremental_tests.py coverage

# Run specific test
uv run python tests/run_incremental_tests.py specific --test-path tests/engine/incremental/test_should_run.py::TestShouldRunIncremental
```

### Using pytest directly

The commands above are summarized here for quick copy-paste:

```bash
# Recommended default: full suite except Snowflake E2E
uv run pytest tests/ -m "not snowflake_e2e" -v

# Everything including Snowflake E2E (requires tests/.snowflake_config.json or env vars)
uv run pytest tests/ -v

# Only Snowflake E2E
uv run pytest tests/ -m snowflake_e2e -v
```

Other useful invocations:

```bash
# Run specific test file
uv run pytest tests/engine/incremental/test_should_run.py -v

# Run specific test class
uv run pytest tests/engine/incremental/test_should_run.py::TestShouldRunIncremental -v

# Run specific test method
uv run pytest tests/engine/incremental/test_should_run.py::TestShouldRunIncremental::test_no_state_exists_runs_full_load -v

# Run with coverage
uv run pytest tests/ --cov=t4t.engine.incremental_executor --cov-report=html

# Run only unit tests
uv run pytest tests/ -m unit -v

# Run only integration tests
uv run pytest tests/ -m integration -v

# Skip slow tests
uv run pytest tests/ -m "not slow" -v

# Stop on first failure
uv run pytest tests/ -x

# Shorter tracebacks
uv run pytest tests/ --tb=short
```

### Parallel execution

Parallel test runs (**pytest-xdist**, e.g. `-n auto`) are **not** wired into this repo by default. They can speed up some suites but are not required; start with **`--no-cov`** before adding workers.

## Test Markers

Tests are marked with categories for easy filtering:

- `@pytest.mark.unit`: Unit tests (fast, isolated)
- `@pytest.mark.integration`: Integration tests (require database)
- `@pytest.mark.slow`: Performance tests (may take longer)
- `@pytest.mark.snowflake_e2e`: Live Snowflake end-to-end tests (applied in `conftest.py` to `tests/adapters/snowflake/*_e2e.py` and `tests/engine/integration/test_function_execution_snowflake.py`). For when to exclude them, see [Choosing what to run](#choosing-what-to-run-with-or-without-snowflake-e2e).

## Test Fixtures

### Shared Fixtures (`conftest.py`)

- `temp_db_path`: Temporary DuckDB database file
- `temp_state_db_path`: Temporary state database file
- `duckdb_config`: DuckDB adapter configuration
- `duckdb_adapter`: Connected DuckDB adapter instance
- `state_manager`: Model state manager instance
- `sample_*_config`: Sample configurations for different strategies
- `sample_table_sql`: Sample table creation SQL
- `sample_data_sql`: Sample data insertion SQL

### Usage Example

```python
def test_my_feature(duckdb_adapter, sample_append_config):
    """Test using shared fixtures."""
    # Use duckdb_adapter and sample_append_config
    result = duckdb_adapter.execute_incremental_append("table", "SELECT 1")
    assert result is not None
```

## Writing New Tests

### For Core Logic

Add tests to the appropriate file in `engine/incremental/`:

```python
# For should_run logic, add to test_should_run.py
# For time filtering, add to test_time_filter.py
# For variable resolution, add to test_variables.py
# etc.

def test_new_feature(executor, sample_config):
    """Test new incremental feature."""
    result = executor.some_method(sample_config)
    assert result == expected_value
```

### For Adapter Interface

Add tests to `test_incremental_adapter_interface.py`:

```python
def test_new_adapter_behavior(mock_adapter):
    """Test new adapter behavior."""
    mock_adapter.some_method.return_value = expected_value
    result = mock_adapter.some_method("param")
    assert result == expected_value
```

### For Parser Features

Add tests to the appropriate parser subdirectory:
- `parser/core/` for project parsing
- `parser/parsers/` for parser implementations
- `parser/processing/` for processing logic
- `parser/shared/` for shared utilities

### For Testing Framework Features

Add tests to `testing/` directory:
- `test_base.py` for base class tests
- `test_executor.py` for executor tests
- `testing/standard_tests/` for standard test implementations (create new file if adding new test type)

### For Database-Specific Features

Add tests to `adapters/` directory (or create new adapter test file):

```python
# For DuckDB functional tests, add to adapters/duckdb/test_incremental.py
# For DuckDB performance tests, add to adapters/duckdb/test_incremental_performance.py
# For other adapters, create adapters/<adapter_name>/ directory

def test_duckdb_specific_feature(duckdb_adapter, sample_table_sql):
    """Test DuckDB-specific feature."""
    duckdb_adapter.execute_query(sample_table_sql)
    result = duckdb_adapter.some_duckdb_method()
    assert result == expected_value
```

## Test Data

### Sample Data Structure

Tests use a consistent sample data structure:

```sql
CREATE TABLE test_schema.source_table (
    id INTEGER,
    name VARCHAR,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    status VARCHAR
);

INSERT INTO test_schema.source_table VALUES
(1, 'Alice', '2024-01-01 10:00:00', '2024-01-01 10:00:00', 'active'),
(2, 'Bob', '2024-01-02 11:00:00', '2024-01-02 11:00:00', 'active'),
(3, 'Charlie', '2024-01-03 12:00:00', '2024-01-03 12:00:00', 'inactive'),
(4, 'David', '2024-01-04 13:00:00', '2024-01-04 13:00:00', 'active'),
(5, 'Eve', '2024-01-05 14:00:00', '2024-01-05 14:00:00', 'active');
```

### Performance Test Data

For performance tests, use the `large_dataset_sql` fixture:

```python
def test_performance(duckdb_adapter, large_dataset_sql):
    """Test with large dataset."""
    duckdb_adapter.execute_query(large_dataset_sql)
    # Run performance test
```

## Best Practices

### 1. Test Isolation

- Each test should be independent
- Use fixtures for setup/teardown
- Clean up temporary files and databases

### 2. Test Naming

- Use descriptive test names
- Follow pattern: `test_what_behavior_when_condition`
- Group related tests in classes

### 3. Test Coverage

- Test happy path scenarios
- Test error conditions
- Test edge cases
- Test performance characteristics

### 4. Mock Usage

- Mock external dependencies
- Mock database operations in unit tests
- Use real database operations in integration tests

### 5. Assertions

- Use specific assertions
- Test both positive and negative cases
- Verify side effects (state changes, method calls)

## Continuous Integration

Tests are designed to run in CI environments:

- No external dependencies beyond test databases
- Temporary files are cleaned up automatically
- Tests are marked for different execution environments
- Performance tests can be skipped in fast CI runs (`-m "not slow"`)
- **Snowflake E2E** often need secrets and significant time; many pipelines run **`pytest -m "not snowflake_e2e"`** on every push and reserve the full suite (or a scheduled job) for environments with Snowflake credentials

## Debugging Tests

### Running with Debug Output

```bash
# Run with maximum verbosity
uv run pytest tests/ -vvv --tb=long

# Run specific test with debug
uv run pytest tests/engine/incremental/test_should_run.py::TestShouldRunIncremental::test_no_state_exists_runs_full_load -vvv --tb=long
```

### Using pytest Debugging

```python
def test_debug_example(duckdb_adapter):
    """Example of debugging test."""
    import pdb; pdb.set_trace()  # Set breakpoint
    result = duckdb_adapter.some_method()
    assert result == expected_value
```

### Logging in Tests

```python
import logging

def test_with_logging(duckdb_adapter):
    """Test with logging enabled."""
    logging.basicConfig(level=logging.DEBUG)
    result = duckdb_adapter.some_method()
    assert result == expected_value
```

## MotherDuck Testing

Tests for MotherDuck (cloud DuckDB) are available in `tests/adapters/duckdb/test_motherduck.py`.

### Setup

To run MotherDuck tests, you need:

1. **Install the MotherDuck extension** for DuckDB:
   ```bash
   duckdb -c "INSTALL motherduck;"
   ```
   Or in Python:
   ```python
   import duckdb
   conn = duckdb.connect()
   conn.execute("INSTALL motherduck;")
   ```

2. **Provide credentials** using one of these methods:

   **Option A: Config file (recommended for local development)**
   ```bash
   # Copy the example file
   cp tests/.motherduck_config.json.example tests/.motherduck_config.json
   # Edit tests/.motherduck_config.json and add your token
   ```

   **Option B: Environment variables**
   ```bash
   export MOTHERDUCK_TOKEN='your_access_token_here'
   export MOTHERDUCK_DB_NAME='test_db'  # optional, defaults to 'test_db'
   export MOTHERDUCK_SCHEMA='test_schema'  # optional, defaults to 'test_schema'
   ```

3. **Database creation**:
   - The database will be created automatically by the adapter if it doesn't exist
   - Or you can create it manually at https://app.motherduck.com/
   - Or set `MOTHERDUCK_DB_NAME` to an existing database name

### Running MotherDuck Tests

```bash
# Run all MotherDuck tests
uv run pytest tests/adapters/duckdb/test_motherduck.py -v

# Run specific test
uv run pytest tests/adapters/duckdb/test_motherduck.py::TestMotherDuckConnection::test_motherduck_connection -v
```

### Security Note

**Never commit your MotherDuck token to git!** Always use environment variables or a secure secret management system. The tests will skip if the token is not set, so it's safe to run the test suite without it.

### Troubleshooting

If you see errors about the MotherDuck extension not being available:
- Ensure the extension is installed (see Setup above)
- The tests will automatically skip if the extension is not properly installed
- Check that your DuckDB version supports the MotherDuck extension

### Test Coverage

The MotherDuck tests cover:
- Basic connection functionality
- Table creation and management
- Token authentication via environment variable
- Token authentication via config extra
- Connection string variants (`md:` and `motherduck:`)

## Contributing

When adding new tests:

1. **Follow existing patterns** in the test files
2. **Add appropriate markers** for test categorization
3. **Update this README** if adding new test categories
4. **Ensure tests are isolated** and don't depend on each other
5. **Add docstrings** explaining what each test verifies
6. **Use descriptive names** for test methods and variables
