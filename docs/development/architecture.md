# Architecture

This document describes the architecture and design of t4t, providing an overview of the system's components, their interactions, and design decisions.

## System Overview

t4t is built with a modular, pluggable architecture that separates concerns into distinct layers:

```
┌─────────────────────────────────────────────────────────────┐
│                      CLI Layer                               │
│  (typer-based commands: run, parse, test, build, seed)      │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                  Execution Layer                              │
│  • executor.py - High-level workflow orchestration          │
│  • ProjectParser - SQL parsing and dependency analysis      │
│  • ModelExecutor - Model execution coordination             │
│  • TestExecutor - Data quality test execution               │
│  • SeedLoader - Static data file loading                    │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                  Engine Layer                                │
│  • ExecutionEngine - Database-agnostic execution            │
│  • IncrementalExecutor - Incremental materialization        │
│  • ModelStateManager - State tracking                       │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                  Adapter Layer                               │
│  • BaseAdapter - Abstract adapter interface                 │
│  • DuckDBAdapter, SnowflakeAdapter, PostgreSQLAdapter       │
│  • SQL Dialect Conversion (SQLglot)                         │
│  • Connection Management                                    │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. CLI Layer (`t4t/cli/`)

The command-line interface built with Typer:

- **`main.py`** - Entry point and command definitions
- **`commands/`** - Individual command implementations
  - `run.py` - Execute models
  - `parse.py` - Parse without execution
  - `test.py` - Run tests
  - `build.py` - Build with tests
  - `seed.py` - Load seed files
  - `debug.py` - Test connections
  - `init.py` - Initialize projects
- **`context.py`** - Shared command context
- **`utils.py`** - CLI utilities

**Design Decisions:**
- Uses Typer for type-safe CLI with automatic help generation
- Commands are thin wrappers around core functionality
- Shared context handles common setup (config loading, logging)

### 2. Execution Layer (`t4t/executor.py`, `t4t/executor_helpers/`)

High-level orchestration of the complete workflow:

- **`executor.py`** - Main execution functions
  - `execute_models()` - Full workflow: compile → execute models
  - `build_models()` - Build with interleaved tests
- **`executor_helpers/`** - Helper functions for execution workflows
  - `shared_helpers.py` - Shared utilities used by both execute and build
    - `validate_compile_results()` - Validates and extracts compilation results
    - `create_empty_execution_results()` - Creates empty results structure
    - `create_empty_build_results()` - Creates empty build results structure
  - `build_helpers.py` - Build-specific helper functions
    - `execute_functions_in_build()` - Executes functions before models
    - `execute_models_with_tests()` - Executes models with interleaved tests
    - `compile_build_results()` - Compiles final build results

**Design Decisions:**
- Separates high-level workflow from low-level execution
- Provides both programmatic and CLI interfaces
- Handles selection filtering and variable substitution
- Shared helpers eliminate code duplication between execute and build
- Specific error handling for `CompilationError` and `ParserError`
- Graceful handling of empty projects (no models)

### 3. Parser Layer (`t4t/parser/`)

SQL parsing, dependency analysis, and graph building:

- **`core/`** - Core parsing components
  - `project_parser.py` - Main ProjectParser class
  - `orchestrator.py` - High-level orchestration
- **`parsers/`** - SQL and Python parsers
  - `sql_parser.py` - SQL file parsing
  - `python_parser.py` - Python metadata parsing
- **`analysis/`** - Dependency analysis
  - `dependency_graph_builder.py` - Builds dependency graphs
  - `table_resolver.py` - Resolves table references
- **`processing/`** - SQL processing
  - Variable substitution
  - SQL validation
- **`output/`** - Output generation
  - JSON export
  - Report generation

**Design Decisions:**
- Layered architecture for maintainability
- Separates parsing, analysis, and output generation
- Supports both SQL and Python metadata files
- Uses SQLglot for SQL parsing and dialect conversion

### 4. Engine Layer (`t4t/engine/`)

Database-agnostic execution engine:

- **`execution_engine.py`** - Main ExecutionEngine class
  - Model execution
  - Schema management
  - Table/view creation
- **`incremental_executor.py`** - Incremental materialization
  - Append strategy
  - Merge strategy
  - Delete+insert strategy
- **`seeds/`** - Seed file loading
  - `seed_discovery.py` - Discovers seed files
  - `seed_loader.py` - Loads seeds into database

**Design Decisions:**
- Database-agnostic interface
- Adapter pattern for database-specific implementations
- State management for incremental models
- Automatic schema creation and management

### 5. Adapter Layer (`t4t/adapters/`)

Database-specific implementations:

- **`base.py`** - BaseAdapter abstract class
- **`duckdb_adapter.py`** - DuckDB implementation
- **`snowflake_adapter.py`** - Snowflake implementation
- **`postgresql_adapter.py`** - PostgreSQL implementation
- **`bigquery_adapter.py`** - BigQuery implementation

**Design Decisions:**
- Pluggable adapter system
- Consistent interface across databases
- Database-specific optimizations
- SQL dialect conversion via SQLglot

### 6. Testing Layer (`t4t/testing/`)

Data quality testing framework:

- **`test_executor.py`** - Test execution
- **`test_types.py`** - Test type definitions
- **`standard_tests.py`** - Built-in standard tests
- **`custom_tests.py`** - Custom SQL test support

**Design Decisions:**
- Extensible test framework
- Standard tests (not_null, unique, etc.)
- Custom SQL tests for complex validations
- Severity levels (error, warning)

## Data Flow

### Model Execution Flow

```
1. CLI Command (run/build/test)
   ↓
2. CommandContext (load config, setup logging)
   ↓
3. executor.execute_models() or executor.build_models()
   ├─→ compile_project() (compile to OTS modules)
   ├─→ shared_helpers.validate_compile_results() (validate compilation)
   └─→ Handle empty projects gracefully
   ↓
4. ProjectParser (parse SQL files)
   ├─→ FileDiscovery (find SQL files)
   ├─→ SQLParser (parse SQL)
   ├─→ PythonParser (parse metadata)
   └─→ DependencyGraphBuilder (build graph)
   ↓
5. ModelExecutor (execute models)
   ├─→ ExecutionEngine (database operations)
   ├─→ Adapter (database-specific)
   └─→ SQL Dialect Conversion (SQLglot)
   ↓
6. TestExecutor (run tests) [build only]
   └─→ Standard/Custom Tests
   ↓
6. Results (return execution results)
```

### Dependency Resolution

```
1. Parse all SQL files
   ↓
2. Extract table references from each model
   ↓
3. Build dependency graph (model → dependencies)
   ↓
4. Topological sort to determine execution order
   ↓
5. Execute in dependency order
```

## Key Design Patterns

### 1. Adapter Pattern

Database adapters provide a consistent interface:

```python
class BaseAdapter(ABC):
    @abstractmethod
    def execute_query(self, sql: str) -> Any:
        pass

    @abstractmethod
    def create_table(self, name: str, sql: str) -> None:
        pass
```

### 2. Strategy Pattern

Incremental materialization strategies:

```python
class IncrementalStrategy(ABC):
    @abstractmethod
    def execute(self, model: ParsedModel) -> None:
        pass
```

### 3. Factory Pattern

Parser factory for different file types:

```python
class ParserFactory:
    @staticmethod
    def create_parser(file_path: Path) -> Parser:
        if file_path.suffix == '.sql':
            return SQLParser()
        elif file_path.suffix == '.py':
            return PythonParser()
```

### 4. Builder Pattern

Dependency graph building:

```python
class DependencyGraphBuilder:
    def add_node(self, model: ParsedModel) -> None:
        ...

    def add_edge(self, from_model: str, to_model: str) -> None:
        ...

    def build(self) -> DependencyGraph:
        ...
```

## State Management

### Incremental Models

State is tracked in the database:

- Execution history
- Last run timestamp
- Incremental state (for merge strategies)
- Model metadata

### Connection Management

- Connection pooling (where supported)
- Automatic reconnection
- Cleanup on exit

## Error Handling

The execution layer uses specific exception handling to provide clear error messages:

- **`CompilationError`** - Raised when project compilation fails
- **`ParserError`** - Raised when parsing SQL or metadata fails
- **`RuntimeError`** - Raised for invalid compilation results (missing graph/execution_order)

Both `execute_models()` and `build_models()` catch these specific exceptions and re-raise them, while wrapping unexpected exceptions in `CompilationError` for consistency.

### Exception Hierarchy

```
ParserError
├─ SQLParsingError
├─ PythonParsingError
├─ DependencyError
└─ VariableSubstitutionError

ExecutionError
├─ ConnectionError
├─ QueryExecutionError
└─ SchemaError

TestError
├─ TestFailureError
└─ TestExecutionError
```

### Error Recovery

- Graceful degradation
- Detailed error messages
- Context preservation
- Cleanup on failure
- Empty project handling (projects with no models execute successfully)

### Execution Layer Error Handling

The execution layer (`executor.py`) implements specific error handling:

- **Compilation Errors**: Catches `CompilationError` and `ParserError` explicitly
- **Unexpected Errors**: Wraps unexpected exceptions in `CompilationError` for consistency
- **Empty Projects**: Gracefully handles projects with no models, returning empty results structures
- **Validation**: Validates compilation results before proceeding with execution

## Configuration Management

### Configuration Sources

1. **`project.toml`** - Project configuration
2. **Environment Variables** - Override defaults
3. **CLI Arguments** - Runtime overrides

### Configuration Hierarchy

```
CLI Arguments > Environment Variables > project.toml > Defaults
```

## Testing Architecture

### Test Types

1. **Unit Tests** - Individual components
2. **Integration Tests** - Component interactions
3. **CLI Tests** - Command-line interface
4. **End-to-End Tests** - Complete workflows

### Test Coverage

- Target: 90%+ coverage
- Focus on critical paths
- Mock external dependencies (databases)

## Performance Considerations

### Optimization Strategies

1. **Parallel Execution** - Where possible (future)
2. **Caching** - Parsed models, dependency graphs
3. **Lazy Loading** - Load only what's needed
4. **Connection Pooling** - Reuse database connections

### Scalability

- Handles large dependency graphs
- Efficient topological sorting
- Incremental execution for large datasets

## Security Considerations

### Credential Management

- Never log credentials
- Support for environment variables
- Secure credential storage (future)

### SQL Injection Prevention

- Parameterized queries where possible
- Input validation
- SQL parsing and validation

## Extension Points

### Adding New Adapters

1. Inherit from `BaseAdapter`
2. Implement required methods
3. Register in adapter factory

### Adding New Test Types

1. Inherit from `TestType`
2. Implement test logic
3. Register in test executor

### Adding New Commands

1. Create command function in `commands/`
2. Register in `main.py`
3. Add tests

## Future Enhancements

### Planned Features

- Parallel model execution
- Advanced caching
- Real-time monitoring
- Web UI (future)
- Plugin system

### Architecture Evolution

- Microservices (if needed)
- API layer
- Event-driven architecture (for large-scale)

## Related Documentation

- [Overview](../user-guide/overview.md) - User-facing overview
- [Execution Engine](../user-guide/execution-engine.md) - Execution engine details
- [Database Adapters](../user-guide/database-adapters.md) - Adapter system
- [Contributing](contributing.md) - How to contribute
