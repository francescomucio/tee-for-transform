# Data Quality Tests

t4t provides a comprehensive data quality testing framework that allows you to automatically validate your data transformations. Tests are defined in model metadata and automatically executed after model creation.

## Overview

The testing framework supports:
- **Standard Tests**: Pre-built tests for common data quality checks
- **Generic SQL Tests**: Reusable SQL tests with placeholders (e.g., `@table_name`, `@column_name`)
- **Singular SQL Tests**: SQL tests with hardcoded table names for table-specific validations
- **Parameterized Tests**: Tests that accept configuration parameters
- **Test Severity Levels**: Control whether tests fail builds (ERROR) or just warn (WARNING)
- **Automatic Execution**: Tests run automatically after models are executed
- **Standalone Execution**: Run tests independently with `t4t test`

## Quick Start

### Basic Test Definition

Tests are defined in your model metadata files:

```python
# models/my_table.py
from t4t.typing import ModelMetadata

metadata: ModelMetadata = {
    "description": "My first table",
    "materialization": "table",
    "schema": [
        {
            "name": "id",
            "datatype": "integer",
            "tests": ["not_null", "unique"]
        },
        {
            "name": "name",
            "datatype": "string",
            "tests": ["not_null"]
        }
    ],
    "tests": ["row_count_gt_0"]
}
```

### Running Tests

Tests are automatically executed after model runs:

```bash
# Run models (tests execute automatically with interleaved execution)
t4t build examples/t_project

# Run models without tests
t4t run examples/t_project

# Run tests independently
t4t test examples/t_project
```

**Note:** The `build` command executes models and tests interleaved (test runs immediately after each model), while `run` executes models without tests. Use `t4t test` to run tests independently.

## Test Definition Formats

Tests can be defined in multiple formats depending on whether they need parameters or severity configuration. Tests can be applied at both the **column level** (within a column definition) and the **table level** (at the model root).

### Simple String Format

For tests without parameters. These are typically applied to columns:

**Column-level example:**
```python
{
    "name": "id",
    "datatype": "integer",
    "tests": ["not_null", "unique"]  # Applied to this column
}
```

**Table-level example:**
```python
{
    "description": "My table",
    "tests": ["row_count_gt_0"]  # Applied to the entire table
}
```

### Dictionary Format

For parameterized tests that require configuration:

**Column-level example:**
```python
{
    "name": "status",
    "datatype": "string",
    "tests": [
        {
            "name": "accepted_values",
            "params": {
                "values": ["active", "inactive"]
            }
        }
    ]
}
```

**Table-level example:**
```python
{
    "description": "My table",
    "tests": [
        {
            "name": "unique",
            "params": {"columns": ["col1", "col2"]}
        }
    ]
}
```

### With Severity Configuration

Configure test severity for non-critical checks:

**Column-level example:**
```python
{
    "name": "optional_field",
    "datatype": "string",
    "tests": [
        {
            "name": "not_null",
            "severity": "warning"  # Won't fail the build
        }
    ]
}
```

**Table-level example:**
```python
{
    "description": "My table",
    "tests": [
        {
            "name": "row_count_gt_0",
            "severity": "warning"
        }
    ]
}
```

## Available Tests

### Column-Level Tests

#### `not_null`
Verifies a column contains no NULL values.

```python
{
    "name": "id",
    "datatype": "integer",
    "tests": ["not_null"]
}
```

**Parameters:** None

**Severity:** ERROR (default)

---

#### `unique`
Verifies values in a column are unique. Also supports composite uniqueness at the table level.

**Single column:**
```python
{
    "name": "id",
    "datatype": "integer",
    "tests": ["unique"]
}
```

**Composite key (table level):**
```python
{
    "description": "My table",
    "tests": [
        {
            "name": "unique",
            "params": {"columns": ["col1", "col2"]}
        }
    ]
}
```

**Entire row uniqueness (table level, no columns specified):**
```python
{
    "description": "My table",
    "tests": ["unique"]  # Checks uniqueness across all columns (entire row)
}
```

**Parameters:**
- `columns` (optional, for table-level): List of columns for composite uniqueness. If omitted at table level, checks all columns (entire row uniqueness)

**Severity:** ERROR (default)

---

#### `accepted_values`
Validates that all values in a column are within a specified list of allowed values.

```python
{
    "name": "status",
    "datatype": "string",
    "tests": [
        {
            "name": "accepted_values",
            "params": {
                "values": ["active", "inactive", "pending"]
            }
        }
    ]
}
```

**Parameters:**
- `values` (required): List of accepted values

**Severity:** ERROR (default)

**Supported Types:** Strings, numbers, and other types (with proper SQL escaping)

---

#### `relationships`
Validates referential integrity by checking that values in a source column exist in a target table's column. Supports both single-column and composite key relationships.

**Single column:**
```python
{
    "name": "user_id",
    "datatype": "integer",
    "tests": [
        {
            "name": "relationships",
            "params": {
                "to": "my_schema.users",
                "field": "id"
            }
        }
    ]
}
```

**Composite key:**
```python
{
    "name": "order_id",
    "datatype": "integer",
    "tests": [
        {
            "name": "relationships",
            "params": {
                "to": "my_schema.products",
                "fields": ["order_id", "product_id"],
                "source_fields": ["order_id", "product_id"]
            }
        }
    ]
}
```

**Parameters:**
- `to` (required): Target table name (fully qualified)
- `field` (required for single column): Target column name
- `fields` (required for composite key): List of target column names
- `source_fields` (optional): List of source column names (defaults to column_name for single column)

**Severity:** ERROR (default)

---

### Model-Level Tests

#### `row_count_gt_0`
Verifies a table has at least one row.

```python
{
    "description": "My table",
    "tests": ["row_count_gt_0"]
}
```

**Parameters:** None

**Severity:** ERROR (default)

**Note:** This test has inverted logic - passes if row_count > 0, fails if row_count == 0

---

#### `unique` (Table-Level - Entire Row)
Verifies no duplicate rows exist in a table. When applied at the table level without specifying columns, it checks if entire rows are duplicates (all columns).

```python
{
    "description": "My table",
    "tests": ["unique"]  # Checks entire row uniqueness (all columns)
}
```

**Parameters:** None (when checking all columns)

**Severity:** ERROR (default)

**Note:** This is the same `unique` test, but applied at table level without columns. It's equivalent to checking uniqueness across all columns in the table.

---

## Test Severity Levels

### ERROR (Default)
- Test failures cause the build to fail
- Exit code: 1
- Blocks execution

### WARNING
- Test failures are logged but don't block execution
- Exit code: 0 (with warnings)
- Useful for non-critical validations

### Setting Severity

**In metadata:**
```python
"tests": [
    {
        "name": "not_null",
        "severity": "warning"
    }
]
```

**Note:** Severity can be set in metadata files, but CLI severity overrides are no longer available. Use metadata files to configure test severity.

---

## Custom SQL Tests

You can create custom SQL tests by placing `.sql` files in a `tests/` folder in your project (alongside the `models/` folder). SQL tests come in two types:

- **Generic SQL Tests**: Reusable tests with placeholders (like `@table_name`) that can be applied to multiple tables
- **Singular SQL Tests**: Tests with hardcoded table names for table-specific validations

These tests work like dbt's generic and singular tests.

### Project Structure

```
examples/t_project/
├── models/
│   └── my_schema/
│       └── my_table.sql
├── tests/
│   ├── my_custom_test.sql
│   └── check_minimum_rows.sql
└── project.toml
```

### SQL Test File Format

SQL tests follow the **dbt pattern**:
- Query returns **rows when test fails**
- **0 rows returned = test passes**
- **1+ rows returned = test fails**

### Available Variables

SQL tests automatically have access to these variables:

- `@table_name` or `{{ table_name }}` - The fully qualified table name (e.g., `my_schema.my_table`)
- `@column_name` or `{{ column_name }}` - Column name (if test is applied to a column)
- Custom parameters from metadata (see Parameterized Tests below)

**Note:** `table_name` and `column_name` are substituted as **identifiers** (unquoted), while other parameters are substituted as **SQL values** (quoted if strings).

**Recommendation:** Use `@` syntax (e.g., `@table_name`) for cleaner, more readable SQL.

### Example: Model-Level Test

```sql
-- tests/check_minimum_rows.sql
-- Check that a table has at least a minimum number of rows

SELECT 1 as violation
FROM @table_name
GROUP BY 1
HAVING COUNT(*) < 5
```

**Usage in model metadata:**
```python
metadata: ModelMetadata = {
    "description": "My table",
    "tests": [
        "check_minimum_rows"  # Uses default min_rows=10
    ]
}
```

### Example: Parameterized Test

```sql
-- tests/check_minimum_rows.sql
-- Accepts min_rows parameter (defaults to 10)

SELECT 1 as violation
FROM @table_name
GROUP BY 1
HAVING COUNT(*) < @min_rows:10
```

**Usage with parameters:**
```python
metadata: ModelMetadata = {
    "description": "My table",
    "tests": [
        {
            "name": "check_minimum_rows",
            "params": {"min_rows": 5}
        }
    ]
}
```

### Example: Column-Level Test

```sql
-- tests/column_not_negative.sql
-- Check that a numeric column has no negative values

SELECT @column_name
FROM @table_name
WHERE @column_name < 0
```

**Usage in column metadata:**
```python
metadata: ModelMetadata = {
    "schema": [
        {
            "name": "amount",
            "datatype": "number",
            "tests": ["column_not_negative"]
        }
    ]
}
```

### Generic SQL Tests vs Singular SQL Tests

SQL tests can be either **generic** (reusable across multiple tables) or **singular** (designed for a single table).

#### Generic SQL Tests (Recommended)

Generic SQL tests use variables like `@table_name` or `{{ table_name }}` to make them reusable across multiple tables. They are referenced in model metadata and automatically substitute the table name when executed.

**Example - Generic SQL Test:**
```sql
-- tests/check_minimum_rows.sql
-- This test can be used on any table

SELECT 1 as violation
FROM @table_name
GROUP BY 1
HAVING COUNT(*) < @min_rows:10
```

**Usage:** Reference the test in multiple models' metadata:
```python
# models/table1.py
metadata: ModelMetadata = {
    "tests": ["check_minimum_rows"]  # Reusable!
}

# models/table2.py
metadata: ModelMetadata = {
    "tests": ["check_minimum_rows"]  # Same test, different table!
}
```

**Benefits:**
- Write once, use on many tables
- Easier to maintain (update in one place)
- Consistent testing across tables

**Important:** Generic SQL tests must be referenced in model metadata to be used. If you create a generic SQL test but never reference it in any model's metadata, t4t will warn you that the test is unused.

#### Singular SQL Tests

Singular SQL tests hardcode the table name directly in the SQL. They are useful when:
- The test logic is specific to one table's structure
- You need to reference multiple tables in one test
- The test has complex table-specific business rules

**Example - Singular SQL Test:**
```sql
-- tests/test_my_first_table.sql
-- This test is specific to my_schema.my_first_table
-- Table name is hardcoded

SELECT id, name
FROM my_schema.my_first_table
WHERE name LIKE '%invalid%'
```

**Usage:** Reference the test only in the specific table's metadata:
```python
# models/my_schema/my_first_table.py
metadata: ModelMetadata = {
    "tests": ["test_my_first_table"]  # Only for this table
}
```

**Note:** Even with hardcoded table names, you still need to reference the test in the model's metadata for it to execute.

**When to Use Each:**
- **Use generic SQL tests** when the validation logic applies to multiple tables
- **Use singular SQL tests** when the validation is unique to one table or requires hardcoded table references

### Variable Substitution

SQL tests support multiple variable syntaxes:

**Jinja-style:**
```sql
FROM {{ table_name }}
WHERE {{ column_name }} = {{ status | default('active') }}
```

**At-sign syntax (recommended):**
```sql
FROM @table_name
WHERE @column_name = @status
```

**Default values:**
```sql
-- Default value syntax
{{ min_rows | default(10) }}
{{ status | default('active') }}
```

### Test Discovery

SQL tests are automatically discovered from the `tests/` folder when:
- Running `t4t test` - Standalone test execution
- Running `t4t build` - Tests execute automatically with interleaved execution (test runs immediately after each model/function)
- Running `t4t run` - Tests do NOT execute automatically (use `t4t build` or `t4t test` for tests)

Function tests are discovered from the `tests/functions/` folder:
- `tests/functions/test_calculate_percentage.sql` → test name `"test_calculate_percentage"`

Test names are derived from file names (without `.sql` extension):
- `tests/my_test.sql` → test name `"my_test"`
- `tests/check_minimum_rows.sql` → test name `"check_minimum_rows"`
- `tests/functions/test_calculate_percentage.sql` → test name `"test_calculate_percentage"`

#### Unused Generic Test Warnings

t4t automatically detects when generic SQL tests (tests with placeholders like `@table_name`) are never used. If you have a generic SQL test in your `tests/` folder that is:
- Not referenced in any model's metadata
- Never executed during test runs

You'll see a warning like this:

```
⚠️  Warnings:
  - Generic SQL test 'check_minimum_rows' is never used. Add it to model metadata to apply it to tables. File: tests/check_minimum_rows.sql
```

**Why this warning exists:**
- Generic SQL tests are designed to be reusable across multiple tables
- They must be explicitly referenced in model metadata to be applied
- If a generic test is never referenced, it's likely an oversight or dead code

**How to fix:**
1. Add the test to the appropriate model's metadata:
   ```python
   metadata: ModelMetadata = {
       "tests": ["check_minimum_rows"]  # Add the test here
   }
   ```
2. Or remove the unused test file if it's no longer needed

**Note:** Singular SQL tests (with hardcoded table names) do not trigger this warning, as they may be intentionally unused or used in specific scenarios.

---

## Test Library Export (OTS Format)

When you compile a project with `t4t compile`, t4t automatically exports your SQL tests to an OTS-compliant test library file. This allows your tests to be shared and used by other OTS-compliant tools.

### Automatic Export

The test library is automatically generated when compiling a project:

```bash
t4t compile examples/t_project
```

This creates a test library file in the `output/ots_modules/` folder:
- **File name**: `{project_name}_test_library.ots.json` (or `.ots.yaml` if using YAML format)
- **Location**: `examples/t_project/output/ots_modules/t_project_test_library.ots.json`
- **Format**: JSON or YAML (consistent with OTS module format)

### Test Library Structure

The exported test library follows the OTS specification format:

```json
{
  "test_library_version": "1.0",
  "description": "Test library for t_project project",
  "generic_tests": {
    "check_minimum_rows": {
      "type": "sql",
      "level": "table",
      "description": "Check that a table has at least a minimum number of rows",
      "sql": "SELECT 1 as violation\nFROM @table_name\nGROUP BY 1\nHAVING COUNT(*) < @min_rows:10",
      "parameters": {
        "min_rows": {
          "type": "number",
          "default": 10,
          "description": "Parameter min_rows"
        }
      }
    }
  },
  "singular_tests": {
    "test_my_first_table": {
      "type": "sql",
      "level": "table",
      "description": "Singular SQL test for my_first_table",
      "sql": "SELECT id, name\nFROM my_schema.my_first_table\nWHERE name LIKE '%invalid%'",
      "target_transformation": "my_schema.my_first_table"
    }
  }
}
```

### OTS Module Integration

When OTS modules are exported, they include a reference to the test library:

```json
{
  "ots_version": "0.1.0",
  "module_name": "t_project.my_schema",
  "test_library_path": "t_project_test_library.ots.json",
  "target": {...},
  "transformations": [...]
}
```

This allows OTS-compliant tools to discover and use your test definitions.

### What Gets Exported

- **Generic SQL Tests**: Tests with placeholders like `@table_name` are exported to `generic_tests`
- **Singular SQL Tests**: Tests with hardcoded table names are exported to `singular_tests`
- **Metadata Extraction**: 
  - Description extracted from SQL comments
  - Parameters extracted from `@param:default` syntax
  - Test level (table/column) inferred from SQL content
  - Target transformation extracted for singular tests

**Note:** Standard tests (like `not_null`, `unique`) are not exported to the test library, as they are defined in the OTS specification itself.

---

## Running Tests

### Automatic Execution

Tests are automatically executed after models are created:

```bash
t4t run examples/t_project
```

Output includes test results:
```
==================================================
EXECUTING TESTS
==================================================

Test Results:
  Total tests: 7
  ✅ Passed: 7
  ❌ Failed: 0

✅ All tests passed!
```

### Standalone Test Execution

Run tests independently without re-running models:

```bash
# Run all tests
t4t test examples/t_project

# Run with verbose output
t4t test examples/t_project --verbose

# Run tests (severity is configured in metadata files)
t4t test examples/t_project

# Run with variables (JSON format)
t4t test ./examples/t_project --vars '{"start_date": "2024-01-01"}'
```

### Test Execution Order

Tests are executed in dependency order, ensuring that:
1. Source tables exist before relationship tests run
2. Models are fully materialized before tests execute
3. Tests run in the same order as model execution

---

## Test Results

### Result Structure

Each test returns a `TestResult` object with:
- `test_name`: Name of the test
- `table_name`: Fully qualified table name
- `column_name`: Column name (if applicable)
- `passed`: Boolean indicating pass/fail
- `message`: Human-readable message
- `severity`: ERROR or WARNING
- `rows_returned`: Number of violating rows (for failed tests)

### Result Categories

Tests are categorized into:
- **Passed**: All tests that passed
- **Failed**: Tests that failed with ERROR severity
- **Warnings**: Tests that failed with WARNING severity or unimplemented tests

### Exit Codes

- **0**: All tests passed (or only warnings)
- **1**: One or more tests failed with ERROR severity

---

## Examples

### Complete Example

```python
# models/orders.py
from t4t.typing import ModelMetadata

metadata: ModelMetadata = {
    "description": "Orders table",
    "materialization": "table",
    "schema": [
        {
            "name": "order_id",
            "datatype": "integer",
            "tests": ["not_null", "unique"]
        },
        {
            "name": "user_id",
            "datatype": "integer",
            "tests": [
                "not_null",
                {
                    "name": "relationships",
                    "params": {
                        "to": "my_schema.users",
                        "field": "id"
                    }
                }
            ]
        },
        {
            "name": "status",
            "datatype": "string",
            "tests": [
                {
                    "name": "accepted_values",
                    "params": {
                        "values": ["pending", "completed", "cancelled"]
                    }
                }
            ]
        },
        {
            "name": "amount",
            "datatype": "decimal",
            "tests": ["not_null"]
        }
    ],
    "tests": [
        "row_count_gt_0",
        "unique"  # Checks entire row uniqueness (all columns)
    ]
}
```

### Configuring Test Severity

Test severity is configured in metadata files (`.py` files) using the `severity` field. See the [Test Severity Levels](#test-severity-levels) section for details on how to set severity in metadata.

Example:
```python
{
    "name": "optional_field",
    "datatype": "string",
    "tests": [
        {
            "name": "not_null",
            "severity": "warning"  # Configured in metadata, not via CLI
        }
    ]
}
```

---

## Best Practices

### General Testing Best Practices

1. **Start with Critical Tests**: Use `not_null` and `unique` for primary keys
2. **Use Relationships**: Validate foreign key integrity with `relationships` tests
3. **Test Data Quality**: Use `accepted_values` for enumerated fields
4. **Monitor Table Health**: Use `row_count_gt_0` to ensure tables aren't empty
5. **Check for Duplicates**: Use `unique` at table level (without columns) for fact tables to check entire row uniqueness
6. **Set Appropriate Severity**: Use WARNING for non-critical checks
7. **Test in CI/CD**: Include `t4t test` in your CI/CD pipeline

### SQL Test Best Practices

1. **Use COUNT(*) for performance** when possible:
   ```sql
   SELECT COUNT(*) as violation_count
   FROM @table_name
   WHERE condition
   HAVING COUNT(*) > 0
   ```

2. **Return rows directly** for simple checks:
   ```sql
   SELECT * FROM @table_name WHERE violation_condition
   ```

3. **Document parameters** in SQL comments:
   ```sql
   -- Accepts: min_rows (default: 10), max_rows (optional)
   ```

4. **Use meaningful test names** that describe what they check
5. **Prefer generic SQL tests** over singular SQL tests when possible for reusability

---

## Troubleshooting

### Unused Generic SQL Tests

If you see a warning about an unused generic SQL test:

```
⚠️  Generic SQL test 'my_custom_test' is never used. Add it to model metadata to apply it to tables. File: tests/my_custom_test.sql
```

This means you have a generic SQL test file that uses placeholders (like `@table_name`) but it's never referenced in any model's metadata.

**Solution:**
1. **Add the test to model metadata** if you want to use it:
   ```python
   # models/my_table.py
   metadata: ModelMetadata = {
       "tests": ["my_custom_test"]  # Add here
   }
   ```

2. **Remove the test file** if it's no longer needed:
   ```bash
   rm tests/my_custom_test.sql
   ```

**Note:** This warning only applies to generic SQL tests. Singular SQL tests (with hardcoded table names) won't trigger this warning.

### Unimplemented Tests

If a test is not implemented, it will show as a warning:

```
⚠️  Test 'unknown_test' not implemented yet. Available tests: ['not_null', 'unique', ...]
```

### Test Failures

When a test fails, check:
1. The test message for specific violation details
2. The `rows_returned` count to see how many rows violate the test
3. The SQL query generated (with `--verbose` flag)

### Performance

For large tables, tests use `COUNT(*)` queries for better performance:
- `not_null`: Uses `COUNT(*) WHERE column IS NULL`
- `unique`: Uses `COUNT(*)` on duplicate groups
- `relationships`: Uses `COUNT(*)` with LEFT JOIN

---

## Extending Tests

### Adding Custom Python Tests

To add a custom Python test class, create a class inheriting from `StandardTest`:

```python
from t4t.testing.base import StandardTest, TestSeverity
from t4t.testing import TestRegistry

class MyCustomTest(StandardTest):
    def __init__(self):
        super().__init__("my_custom_test", severity=TestSeverity.ERROR)
    
    def validate_params(self, params, column_name):
        # Validate parameters
        pass
    
    def get_test_query(self, adapter, table_name, column_name, params):
        # Generate SQL query
        return f"SELECT COUNT(*) FROM {table_name} WHERE ..."
    
    def check_passed(self, count):
        # Custom logic for determining pass/fail
        return count == 0

# Register the test
MY_CUSTOM_TEST = MyCustomTest()
TestRegistry.register(MY_CUSTOM_TEST)
```

### Database-Specific Optimizations

Adapters can override test query generation for database-specific optimizations:

```python
class MyAdapter(DatabaseAdapter):
    def generate_not_null_test_query(self, table_name, column_name):
        # Database-specific SQL generation
        return f"SELECT COUNT(*) FROM {table_name} WHERE {column_name} IS NULL"
```

---

## Function Tests

Functions can be tested using SQL tests in the `tests/functions/` folder. Function tests support two patterns:

### Assertion-Based Tests (Default)

The test SQL returns a boolean - `TRUE` means the test passed:

```sql
-- tests/functions/test_calculate_percentage.sql
SELECT 
    my_schema.calculate_percentage(10.0, 20.0) = 50.0 AS test_passed
```

### Expected Value Tests

The test SQL returns a value, and the expected value is specified in function metadata:

```python
# functions/my_schema/calculate_percentage.py
metadata = {
    "function_name": "calculate_percentage",
    "tests": [
        {
            "name": "test_calculate_percentage",
            "expected": 50.0,
            "params": {"numerator": 10.0, "denominator": 20.0}
        }
    ]
}
```

```sql
-- tests/functions/test_calculate_percentage.sql
SELECT 
    my_schema.calculate_percentage(@param1, @param2) AS result
```

### Function Test Placeholders

Function tests support placeholders:
- `@function_name` or `{{ function_name }}` - The function name
- `@param1`, `@param2`, etc. - Function parameters from test metadata

**Note:** For complete documentation on function testing, including detailed examples and best practices, see the [Functions Guide](functions.md#function-testing).

## Related Documentation

- [Functions](functions.md) - User-Defined Functions (UDFs) and function testing
- [Execution Engine](execution-engine.md) - Learn about model execution
- [Database Adapters](database-adapters.md) - Database-specific features
- [Examples](examples/README.md) - Practical usage examples

