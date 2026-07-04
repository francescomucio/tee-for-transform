# Configuration

t4t loads database and project settings from TOML files in your **project directory** (the folder you pass to `t4t run`, `t4t debug`, etc.) and from **environment variables**. The loader is `DatabaseConfigManager` in `tee/engine/config.py`.

## Which file is read?

For a given project folder, the loader opens **one** file:

1. If **`pyproject.toml`** exists in that folder, it is used.
2. Otherwise, if **`project.toml`** exists, it is used.
3. If neither exists, configuration falls back to environment variables only (if set).

There is **no merge** of `pyproject.toml` and `project.toml` in the same directory—whichever exists first wins. This matters if you keep both files side by side: only `pyproject.toml` is read.

**Typical workflow:** `t4t init` creates **`project.toml`** with `[connection]` and `[flags]`. That is the primary format documented below.

## `project.toml` (CLI projects)

Example aligned with `t4t init` (DuckDB):

```toml
project_folder = "my_project"

[connection]
type = "duckdb"
path = "data/my_project.duckdb"

[flags]
materialization_change_behavior = "warn"  # warn | error | ignore
```

### Connection keys

Use the keys your database expects (same as in `t4t init` templates):

| Backend    | Common keys |
|-----------|-------------|
| DuckDB    | `type`, `path` (e.g. `data/name.duckdb`, `:memory:`, or `md:...` for MotherDuck) |
| Snowflake | `type`, `host`, `user`, `password`, `role`, `warehouse`, `database` |
| PostgreSQL | `type`, `host`, `port`, `database`, `user`, `password` |
| BigQuery  | `type`, `project`, `database` (dataset) |

Optional nested settings can go under **`[connection.extra]`** (for example MotherDuck token placeholders from `t4t init -d motherduck`). Prefer **`MOTHERDUCK_TOKEN`** in the environment over committing secrets.

### SQL dialect

In TOML, set either:

- `source_sql_dialect` (preferred name in project config), or  
- `source_dialect` (supported alias)

Either is mapped to the adapter’s source dialect for SQL conversion. See [SQL Dialect Conversion](../user-guide/sql-dialect-conversion.md).

### `[flags]`

Top-level `[flags]` in `project.toml` / `pyproject.toml` is passed through (e.g. `materialization_change_behavior`). Other flags may be documented in the user guide as they are added.

## `pyproject.toml` alternative (`[tool.tee]`)

If you use **`pyproject.toml`** as the single config file, you can put the database section under **`[tool.t4t.database]`**, or define multiple named configs under **`[tool.t4t.databases.<name>]`** and load by name in code (`load_database_config("dev")`).

Example equivalent to a simple DuckDB `project.toml`:

```toml
[tool.t4t.database]
type = "duckdb"
path = "data/my_project.duckdb"
source_sql_dialect = "postgresql"
```

Precedence inside the file: `[tool.t4t.database]` or a matching `[tool.t4t.databases.<config_name>]` entry is used before a legacy **`[connection]`** block in the same file.

## Environment variables

These override values loaded from TOML (last-write wins in the merged dict):

| Variable | Maps to |
|----------|---------|
| `TEE_DB_TYPE` | `type` |
| `TEE_DB_HOST` | `host` |
| `TEE_DB_PORT` | `port` |
| `TEE_DB_DATABASE` | `database` |
| `TEE_DB_USER` | `user` |
| `TEE_DB_PASSWORD` | `password` |
| `TEE_DB_PATH` | `path` |
| `TEE_DB_SCHEMA` | `schema` |
| `TEE_DB_WAREHOUSE` | `warehouse` |
| `TEE_DB_ROLE` | `role` |
| `TEE_DB_PROJECT` | `project` |
| `TEE_DB_SOURCE_DIALECT` | `source_dialect` |
| `TEE_DB_TARGET_DIALECT` | `target_dialect` |

Use env vars for secrets and environment-specific overrides.

## Programmatic loading

```python
from t4t.engine.config import load_database_config

# Project root = directory containing project.toml or pyproject.toml
config = load_database_config(project_root="/path/to/my_project")
```

Named configs (from `[tool.t4t.databases.*]` only):

```python
config = load_database_config("staging", project_root="/path/to/my_project")
```

You can also build an [`AdapterConfig`](../api-reference/adapters/README.md) directly for advanced or embedded use cases.

## Schema- and module-level tags

Table/schema tagging can be configured in TOML as described in [Tags and Metadata](../user-guide/tags-and-metadata.md) (`[module]`, `[schemas.<name>]`).

## Troubleshooting

- **Wrong database / empty config:** Confirm you are not keeping both `pyproject.toml` and `project.toml` in the project folder unless `pyproject.toml` is intentional—it hides `project.toml`.
- **MotherDuck auth:** Use `MOTHERDUCK_TOKEN`; avoid committing tokens.
- **Debug loading:** Enable logging at `DEBUG` while calling `load_database_config` to see which file and keys are used.

## Next steps

- [Database Adapters](../user-guide/database-adapters.md)
- [Tags and Metadata](../user-guide/tags-and-metadata.md)
- [SQL Dialect Conversion](../user-guide/sql-dialect-conversion.md)
- [Examples](../user-guide/examples/README.md)
