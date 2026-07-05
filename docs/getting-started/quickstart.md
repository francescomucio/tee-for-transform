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

## 5. Add a Test

Create a test to verify your data:

```bash
mkdir -p demo_project/tests
echo "SELECT * FROM hello WHERE id IS NULL" > demo_project/tests/check_not_null.sql
```

Run tests:

```bash
t4t test demo_project
```

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
| `t4t test` | Ran your test SQL against the database |
| `t4t docs` | Generated interactive documentation with dependency graph |

## Next Steps

- [Configuration](configuration.md) — Customize database connections
- [Data Quality Tests](../user-guide/data-quality-tests.md) — Add more tests
- [Python Models](../api-reference/models.md) — Use the `@model` decorator
- [dbt Users Guide](dbt-users-guide.md) — Coming from dbt?
