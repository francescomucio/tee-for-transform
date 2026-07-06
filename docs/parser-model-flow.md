# Model Parser Flow

This document explains how the parser handles models in three different scenarios.

## Overview

The parser discovers and processes models in two phases:
1. **Discovery Phase**: Finds all `.sql` and `.py` files in the `models/` folder
2. **Parsing Phase**: Processes each file type independently, then merges results

## Three Scenarios

### Scenario 1: Only `.sql` File

**Example**: `models/my_schema/my_table.sql`

**Flow**:
```
1. FileDiscovery discovers: models/my_schema/my_table.sql
2. Orchestrator processes SQL files:
   ├─ Reads SQL content
   ├─ Applies variable substitution (if variables provided)
   ├─ Generates full table name: "my_schema.my_table"
   └─ Calls SQLParser.parse()
3. SQLParser.parse():
   ├─ Parses SQL with sqlglot
   ├─ Extracts dependencies (source tables, functions)
   ├─ Tries to find companion .py file for metadata:
   │  └─ Checks: models/my_schema/my_table.py (via find_metadata_file())
   │     ├─ If found: Parses metadata from Python file
   │     └─ If not found: Tries to extract metadata from SQL comments
   └─ Returns structured model:
      {
        "code": {
          "sql": {
            "original_sql": "...",
            "resolved_sql": "...",
            "operation_type": "select",
            "source_tables": [...],
            "source_functions": [...]
          }
        },
        "model_metadata": {...},
        "sqlglot_hash": "..."
      }
4. Model added to parsed_models dict with key "my_schema.my_table"
```

**Key Points**:
- SQL file is the primary source of truth
- Companion `.py` file (if exists) is only used for metadata (description, schema, tests, materialization)
- If no companion `.py`, metadata can come from SQL comments: `-- metadata: {...}`

---

### Scenario 2: `.py` and `.sql` File (Companion Files)

**Example**:
- `models/my_schema/my_table.sql` (SQL)
- `models/my_schema/my_table.py` (Python metadata)

**Flow**:
```
1. FileDiscovery discovers BOTH files:
   ├─ models/my_schema/my_table.sql
   └─ models/my_schema/my_table.py

2. Orchestrator processes SQL files first:
   ├─ Reads SQL content from .sql file
   ├─ Calls SQLParser.parse()
   └─ SQLParser._parse_metadata():
      └─ find_metadata_file() finds companion .py
         └─ parse_metadata_from_python_file() extracts:
            - description
            - schema (columns with types, descriptions, tests)
            - materialization
            - tests
            - incremental config
            - partitions
   └─ Returns model with SQL code + Python metadata

3. Orchestrator processes Python files:
   ├─ Reads Python content from .py file
   ├─ Calls PythonParser.parse()
   └─ PythonParser checks for @model decorators:
      └─ If found: Creates separate model(s) from Python file
         (Python models are independent - they don't merge with SQL)

4. Result: TWO separate models (if Python has @model decorator):
   ├─ "my_schema.my_table" (from SQL file, with metadata from .py)
   └─ Potentially another model if .py has @model decorator
```

**Key Points**:
- SQL file provides the SQL code
- Python file provides metadata (schema, tests, etc.)
- If Python file has `@model` decorator, it creates a SEPARATE model
- The companion relationship is one-way: SQL → Python (for metadata)

---

### Scenario 3: Only `.py` File

**Example**: `models/my_schema/my_table.py`

**Flow**:
```
1. FileDiscovery discovers: models/my_schema/my_table.py

2. Orchestrator processes Python files:
   ├─ Reads Python content
   └─ Calls PythonParser.parse()

3. PythonParser.parse():
   ├─ Parses AST to find:
   │  ├─ @model decorated functions
   │  └─ create_model() calls
   ├─ For each model found:
   │  ├─ Extracts metadata from decorator/call
   │  ├─ Creates model structure with:
   │  │  {
   │  │    "model_metadata": {
   │  │      "table_name": "...",
   │  │      "function_name": "...",
   │  │      "description": "...",
   │  │      ...
   │  │    },
   │  │    "code": None,  # Will be populated during evaluation
   │  │    "needs_evaluation": True
   │  │  }
   │  └─ Does NOT execute the function yet
   └─ Returns dict of models

4. Orchestrator.evaluate_python_models():
   ├─ For each model with needs_evaluation=True:
   │  ├─ Executes the Python function (injects variables if provided)
   │  ├─ Gets SQL string from function return value
   │  ├─ Validates SQL syntax with sqlglot
   │  ├─ Calls SQLParser.parse() on the returned SQL string
   │  └─ Updates model with parsed SQL code:
   │     {
   │       "code": {
   │         "sql": {
   │           "original_sql": "...",
   │           "resolved_sql": "...",
   │           ...
   │         }
   │       },
   │       "needs_evaluation": False
   │     }
   └─ Returns updated models

5. Model added to parsed_models dict
```

**Key Points**:
- Python file is the source of truth
- Function must return SQL string
- Function is executed at evaluation time (not during AST parsing)
- No companion SQL file is looked for (Python generates SQL dynamically)
- For `create_model()` calls, SQL is extracted from AST (no execution needed)

---

## Important Notes

### File Naming Convention
- Companion files must have the same base name:
  - `my_table.sql` ↔ `my_table.py`
- Different names = separate models

### Model Identification
- SQL models: Table name = `{schema}.{filename}` (from folder structure)
- Python models: Table name = from `@model(table_name="...")` decorator or `create_model(table_name="...")` call

### Evaluation Order
1. SQL files parsed immediately (SQL is static)
2. Python files parsed (AST analysis only)
3. Python models evaluated (functions executed, SQL extracted)
4. All models ready for execution

### Metadata Priority
For SQL files with companion Python:
1. First tries companion `.py` file
2. Falls back to SQL comments: `-- metadata: {...}`
3. If neither found, uses defaults

### Python Model Types

**Type 1: Decorated Functions**
```python
@model(table_name="my_table")
def create_my_table():
    return "SELECT * FROM source"
```
- Detected via AST (looks for `@model` decorator)
- Function executed during evaluation phase

**Type 2: create_model() Calls**
```python
create_model(
    table_name="my_table",
    sql="SELECT * FROM source"
)
```
- Detected via AST (looks for `create_model()` calls)
- SQL extracted directly from AST (no execution needed)
- Supports loops with variable substitution

**Type 3: SqlModelMetadata Auto-Instantiation**
```python
# models/my_schema/my_table.py
metadata: ModelMetadata = {
    "materialization": "table",
    "schema": [...]
}
# Companion file: models/my_schema/my_table.sql
```
- Detected after Python file execution (checks for `metadata` variable)
- Requires companion `.sql` file (same name, different extension)
- Automatically instantiates `SqlModelMetadata` if conditions are met
- Skips auto-instantiation if model already registered from this file
- Handles errors gracefully (warnings for conflicts/parsing errors, debug for others)

---

## Code Locations

- **Orchestrator**: `t4t/parser/core/orchestrator.py` - `discover_and_parse_models()`
- **SQL Parser**: `t4t/parser/parsers/sql_parser.py` - `parse()`, `_parse_metadata()`
- **Python Parser**: `t4t/parser/parsers/python_parser.py` - `parse()`, `evaluate_model_function()`
- **File Discovery**: `t4t/parser/processing/file_discovery.py`
- **Companion File Finder**: `t4t/parser/shared/file_utils.py` - `find_metadata_file()`
