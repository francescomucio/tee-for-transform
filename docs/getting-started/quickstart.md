# 5-Minute Quickstart

Get started with t4t in under 5 minutes. All you need is Python and 5 minutes.

## 1. Install t4t

```bash
pip install t4t
```

That's it. DuckDB is included — no extra database drivers needed.

## 2. Create a Project

```bash
t4t init demo_project
```

This creates:
```
demo_project/
├── project.toml    # Configuration (DuckDB by default)
├── models/         # Your SQL and Python models
├── tests/          # Data quality tests
├── seeds/          # Static data files
└── data/           # DuckDB database file
```

## 3. Add a Model

Create a simple SQL model:

```bash
echo "SELECT 1 AS id, 'hello t4t' AS message" > demo_project/models/hello.sql
```

## 4. Run It

```bash
t4t run demo_project
```

You'll see output like:
```
[INFO] Running model: hello
[INFO] Model hello completed successfully
```

Your model is now a table in DuckDB. You can query it with any DuckDB-compatible tool.

## 5. Add Tests

Tests are declared in model metadata: create a companion `.py` file next to
`hello.sql` (same name, `.py` extension) that describes the model's schema and
which tests to run:

```bash
cat > demo_project/models/hello.py << 'EOF'
from t4t.parser.processing.model_builder import SqlModelMetadata
from t4t.typing.metadata import ModelMetadata

metadata: ModelMetadata = {
    "schema": [
        {"name": "id", "datatype": "number", "tests": ["not_null", "unique"]},
        {"name": "message", "datatype": "string", "tests": ["not_null"]},
    ],
    "tests": ["row_count_gt_0"],
}

model = SqlModelMetadata(metadata)
EOF
```

Run the tests:

```bash
t4t test demo_project
```

You'll see 4 tests pass: `not_null` and `unique` on `id`, `not_null` on
`message`, and a table-level row-count check. Beyond these standard tests you
can write reusable SQL tests with parameters — see
[Data Quality Tests](../user-guide/data-quality-tests.md).

## 6. Generate Documentation

```bash
t4t docs demo_project
```

This generates a static documentation site with your model's dependency graph and metadata.

## What Just Happened?

| Step | What t4t Did |
|---|---|
| `t4t init` | Created project structure with DuckDB config |
| `t4t run` | Parsed your SQL, detected dependencies, executed against DuckDB, materialized as a table |
| `t4t test` | Ran the tests declared in your model metadata against the database |
| `t4t docs` | Generated interactive documentation with dependency graph |

## Next Steps

- [Configuration](configuration.md) — Customize database connections
- [Data Quality Tests](../user-guide/data-quality-tests.md) — Add more tests
- [Python Models](../api-reference/models.md) — Use the `@model` decorator
- [dbt Users Guide](dbt-users-guide.md) — Coming from dbt?
