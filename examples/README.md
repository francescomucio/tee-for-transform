# Example Projects

This directory contains example projects demonstrating various features of Tee. These projects serve as templates and learning resources for building your own data transformation pipelines.

## Available Examples

### `t_project` - DuckDB Example

A complete example project using **DuckDB** as the database backend. This project demonstrates:

- **Basic SQL Models**: Simple table transformations
- **Incremental Materialization**: Examples of append, merge, and delete+insert strategies
- **Python Models**: Auto-generated tables using Python functions
- **Data Quality Tests**: Built-in tests (not_null, unique, row_count_gt_0, etc.)
- **Metadata**: Schema definitions, descriptions, and test configurations
- **Dependency Management**: Models with dependencies on other models

**To run:**
```bash
cd examples/t_project
uv run t4t run .
```

**To run tests:**
```bash
uv run t4t test .
```

### `t_project_sno` - Snowflake Example

A complete example project using **Snowflake** as the database backend. This project demonstrates:

- **Snowflake-Specific Features**: Connection configuration, warehouse, and role management
- **Cross-Database Compatibility**: Same models work with different database backends
- **SQL Dialect Conversion**: Automatic conversion from source SQL to Snowflake dialect
- **Metadata Propagation**: Column descriptions and schema metadata in Snowflake
- **Data Quality Tests**: All standard tests work with Snowflake

**To run:**
```bash
cd examples/t_project_sno
uv run t4t run .
```

**To run tests:**
```bash
uv run t4t test .
```

**Note**: This example requires valid Snowflake credentials configured in `project.toml`.

## Project Structure

Each example project follows the standard Tee project structure:

```
project_name/
├── project.toml          # Project configuration
├── models/               # SQL and Python model files
│   └── schema_name/      # Schema-organized models
│       ├── model.sql     # SQL model files
│       ├── model.py      # Python model files
│       └── model_metadata.py  # Optional metadata files
├── tests/                # Custom SQL test files (optional)
├── data/                 # Local database files (DuckDB)
└── output/               # Generated analysis files (optional)
```

## Key Features Demonstrated

### 1. Incremental Materialization

See `t_project/models/my_schema/incremental_example.sql` for examples of:
- **Append Strategy**: Adding new rows based on time filters
- **Merge Strategy**: Upsert operations with unique keys
- **Delete+Insert Strategy**: Full refresh of specific partitions

### 2. Python Models

See `t_project/models/my_schema/my_auto_table_*.py` for examples of:
- Python functions that return SQL strings
- Auto-generated table schemas
- Metadata defined in Python

### 3. Data Quality Tests

Both projects include examples of:
- **Column-level tests**: `not_null`, `unique`, `accepted_values`
- **Table-level tests**: `row_count_gt_0`, `no_duplicates`
- **Relationship tests**: Foreign key validation

### 4. Metadata

Examples show how to define:
- Column schemas with data types and descriptions
- Table descriptions
- Test configurations
- Materialization strategies

## Using These Examples

### As Templates

You can copy an example project as a starting point:

```bash
cp -r examples/t_project my_new_project
cd my_new_project
# Edit project.toml with your configuration
# Add your models to models/
```

### As Learning Resources

- Study the model files to understand Tee's syntax and features
- Run the projects to see how models execute
- Modify models to experiment with different configurations
- Check the generated `output/` directory for dependency graphs and analysis

### As Test Projects

These projects are also used for:
- Integration testing
- Feature validation
- Documentation examples

## Configuration

Each project has a `project.toml` file that configures:
- **Database connection**: Type, credentials, and connection parameters
- **Project settings**: Schema defaults, flags, and behavior options
- **Metadata**: Project-level tags and descriptions

See the [Configuration Documentation](../../docs/getting-started/configuration.md) for details.

## Notes

- These are example projects - modify them as needed for your use case
- The `output/` directories contain generated files and can be safely deleted
- Database files in `data/` are created automatically when running models
- Snowflake example requires valid credentials - update `project.toml` with your own

## Getting Help

- See the [main README](../../README.md) for installation and setup
- Check the [User Guide](../../docs/user-guide/) for detailed documentation
- Review [Examples Documentation](../../docs/user-guide/examples/) for more examples
