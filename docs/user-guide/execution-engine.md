# Execution Engine

The Execution Engine is a powerful component that can execute parsed SQL models against different databases. It provides a unified interface for running SQL models in the correct dependency order, with support for multiple database backends.

## Features

- **Multi-Database Support**: Currently supports DuckDB, SQLite, and PostgreSQL
- **Dependency-Aware Execution**: Executes models in the correct order based on dependencies
- **Incremental Materialization**: Support for append, merge, and delete+insert strategies
- **Table Reference Resolution**: Automatically resolves table references and aliases
- **Schema Management**: Automatically creates schemas and handles table creation with tag support
- **State Management**: Tracks incremental model state and execution history
- **Comprehensive Logging**: Detailed logging for debugging and monitoring
- **Error Handling**: Robust error handling with detailed error messages
- **Tag Support**: Automatic attachment of tags and metadata to database objects (Snowflake)

## Supported Databases

### DuckDB (Default)
```python
config = {
    "type": "duckdb",
    "path": "path/to/database.duckdb"
}
```

### SQLite
```python
config = {
    "type": "sqlite",
    "path": "path/to/database.db"
}
```

### PostgreSQL
```python
config = {
    "type": "postgresql",
    "host": "localhost",
    "port": 5432,
    "database": "mydb",
    "user": "username",
    "password": "password"
}
```

## Usage

### Basic Usage

```python
from project_parser import ProjectParser, ExecutionEngine

# Configuration
config = {
    "project_folder": "my_project",
    "connection": {
        "type": "duckdb",
        "path": "my_project/data/database.duckdb"
    }
}

# Parse and execute models
parser = ProjectParser(config["project_folder"], config["connection"])
parsed_models = parser.collect_models()
execution_order = parser.get_execution_order()

# Execute models
execution_engine = ExecutionEngine(config["connection"])
execution_engine.connect()

try:
    results = execution_engine.execute_models(parsed_models, execution_order)
    print(f"Successfully executed {len(results['executed_tables'])} tables")
    print(f"Failed: {len(results['failed_tables'])} tables")
finally:
    execution_engine.disconnect()
```

### Single Model Execution

```python
# Execute a single model
result = execution_engine.execute_single_model("my_table", "SELECT * FROM source_table")
if result["status"] == "success":
    print(f"Table created with {result['table_info']['row_count']} rows")
```

## Incremental Materialization

t4t supports three incremental materialization strategies for efficient data processing:

### Append Strategy
Adds new records to existing tables without modifying existing data.

```python
# Configuration
"incremental": {
    "strategy": "append",
    "append": {
        "filter_column": "created_at",
        "start_value": "2024-01-01",
        "lookback": "7 days"
    }
}
```

### Merge Strategy
Performs upsert operations, updating existing records and inserting new ones.

```python
# Configuration
"incremental": {
    "strategy": "merge",
    "merge": {
        "unique_key": ["id"],
        "filter_column": "updated_at",
        "start_value": "auto",
        "lookback": "3 hours"
    }
}
```

### Delete+Insert Strategy
Removes old data and inserts fresh data for a specific time range.

```python
# Configuration
"incremental": {
    "strategy": "delete_insert",
    "delete_insert": {
        "where_condition": "updated_at >= @start_date",
        "filter_column": "updated_at",
        "start_value": "@start_date"
    }
}
```

For detailed information, see the [Incremental Materialization Guide](incremental-materialization.md).

## Architecture

### Core Components

1. **DatabaseConnection (Abstract Base Class)**: Defines the interface for database connections
2. **DuckDBConnection**: DuckDB-specific implementation
3. **SQLiteConnection**: SQLite-specific implementation
4. **PostgreSQLConnection**: PostgreSQL-specific implementation
5. **ExecutionEngine**: Main orchestrator that manages execution
6. **IncrementalExecutor**: Handles incremental materialization strategies
7. **ModelStateManager**: Tracks incremental model state and execution history

### Key Features

#### Table Reference Resolution
The execution engine automatically resolves table references in SQL queries:

```sql
-- Original query
SELECT t1.*, t2.*
FROM my_first_table AS t1
INNER JOIN my_second_table AS t2
ON my_first_table.id = my_second_table.id;

-- Resolved query (for DuckDB with schema)
SELECT t1.*, t2.*
FROM my_schema.my_first_table AS t1
INNER JOIN my_schema.my_second_table AS t2
ON t1.id = t2.id;
```

#### Dependency-Aware Execution
Models are executed in the correct order based on their dependencies:

```python
# Get execution order
execution_order = parser.get_execution_order()
# Returns: ['my_schema.table1', 'my_schema.table2', 'my_schema.table3']

# Execute in dependency order
results = execution_engine.execute_models(parsed_models, execution_order)
```

#### Schema Management
The execution engine automatically creates schemas and handles table creation:

```python
# Schema is automatically created if it doesn't exist
# Tables are created with CREATE OR REPLACE TABLE (DuckDB) or CREATE TABLE IF NOT EXISTS (SQLite/PostgreSQL)
# Schema-level tags are automatically attached when schemas are created (Snowflake)
```

#### Model Selection with Tags
Models can be filtered by tags during execution:

```bash
# Run only models with specific tags
uv run t4t run ./my_project --select tag:analytics

# Exclude models with specific tags
uv run t4t run ./my_project --exclude tag:test
```

See [Tags and Metadata](tags-and-metadata.md) for complete documentation on tagging.

## Error Handling

The execution engine provides comprehensive error handling:

```python
results = execution_engine.execute_models(parsed_models, execution_order)

# Check results
if results["failed_tables"]:
    for failure in results["failed_tables"]:
        print(f"Failed: {failure['table']} - {failure['error']}")

# Check execution log
for log_entry in results["execution_log"]:
    print(f"{log_entry['table']}: {log_entry['status']}")
```

## Logging

The execution engine provides detailed logging:

```python
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
# or for debug information
logging.basicConfig(level=logging.DEBUG)
```

## Extending to New Databases

To add support for a new database, create a new class that inherits from `DatabaseConnection`:

```python
class MyDatabaseConnection(DatabaseConnection):
    def __init__(self, connection_config: Dict[str, Any]):
        super().__init__(connection_config)
        # Initialize your database client

    def connect(self) -> None:
        # Establish connection
        pass

    def disconnect(self) -> None:
        # Close connection
        pass

    def execute_query(self, query: str) -> Any:
        # Execute query and return results
        pass

    def create_table(self, table_name: str, query: str, table_mapping: Dict[str, str] = None) -> None:
        # Create table from query
        pass

    def table_exists(self, table_name: str) -> bool:
        # Check if table exists
        pass

    def drop_table(self, table_name: str) -> None:
        # Drop table
        pass

    def get_table_info(self, table_name: str) -> Dict[str, Any]:
        # Get table information
        pass
```

Then update the `ExecutionEngine._create_connection()` method to support your new database type.

## Example Output

```
==================================================
EXECUTING SQL MODELS
==================================================
Connected to database successfully

Executing 4 models in dependency order...
Execution order: my_schema.my_first_table -> my_schema.my_forth_table -> my_schema.my_second_table -> my_schema.my_third_table

Execution Results:
  Successfully executed: 4 tables
  Failed: 0 tables

Successfully executed tables:
  - my_schema.my_first_table: 2 rows
  - my_schema.my_forth_table: 1 rows
  - my_schema.my_second_table: 2 rows
  - my_schema.my_third_table: 2 rows

Database Info:
  Type: duckdb
  Connected: True
Disconnected from database
```

## Dependencies

- **DuckDB**: `uv add duckdb`
- **SQLite**: Built-in with Python
- **PostgreSQL**: `uv add psycopg2-binary`

## Best Practices

1. **Always use try/finally blocks** to ensure database connections are properly closed
2. **Check execution results** to handle any failures gracefully
3. **Use appropriate logging levels** for your use case
4. **Test with different database types** to ensure compatibility
5. **Handle schema creation** appropriately for your database type
