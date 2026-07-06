# Configuration

t4t loads database and project settings from TOML files in your **project directory** (the folder you pass to `t4t run`, `t4t debug`, etc.) and from **environment variables**. The loader is `DatabaseConfigManager` in `t4t/engine/config.py`.

## Which file is read?

For a given project folder, the loader opens **one** file:

1. If **`project.toml`** exists in that folder, it is used.
2. Otherwise, if **`pyproject.toml`** exists, it is used.
3. If neither exists, configuration falls back to environment variables only (if set).

There is **no merge** of `pyproject.toml` and `project.toml` in the same directory—`project.toml` is preferred because `pyproject.toml` may belong to a parent Python project and contain no t4t configuration.

**Typical workflow:** `t4t init` creates **`project.toml`** with `[environments.*]` sections. That is the primary format documented below.

## `project.toml` (CLI projects)

Example aligned with `t4t init` (DuckDB):

```toml
project_folder = "my_project"

[environments.dev.connection]
type = "duckdb"
path = "data/my_project.duckdb"

[flags]
materialization_change_behavior = "warn"  # warn | error | ignore
```

### Environment sections

Every project must define at least one `[environments.<name>]` section. The `[connection]` top-level section is **no longer supported** — migrate to `[environments.<name>.connection]`.

```toml
[environments.dev.connection]
type = "duckdb"
path = "data/dev.duckdb"

[environments.prod]
protected = true
[environments.prod.connection]
type = "snowflake"
database = "ANALYTICS"
# ...
```

**`[environments.default]`** provides shared config inherited by all environments:

```toml
[environments.default.connection]
type = "duckdb"
path = "data/default.duckdb"
warehouse = "COMPUTE_WH"

[environments.dev.connection]
path = "data/dev.duckdb"  # overrides path, inherits type and warehouse
```

### Environment variables

| Variable | Purpose |
|----------|---------|
| `T4T_ENV` | Default environment name (overridden by `--env`) |
| `T4T_DB_TYPE`, `T4T_DB_HOST`, … | Legacy single-database overrides |
| `ENVIRONMENTS__<NAME>__CONNECTION__<KEY>` | DLT-style per-env overrides (highest precedence) |

Precedence (highest to lowest):

1. `ENVIRONMENTS__*__*` env var (dlt-style, automatic)
2. `T4T_DB_*` env var (legacy)
3. `env:` / `file:` reference in TOML (explicit)
4. Literal value in TOML

### Secret references

Use `env:` or `file:` prefixes instead of plaintext credentials:

```toml
[environments.prod.connection]
password = "env:SNOWFLAKE_PASSWORD"       # from env var
# password = "file:/run/secrets/sf_pw"    # from mounted file
```

Literal passwords trigger a warning. Resolved secrets are redacted in all logs.

### Multi-engine (additional named connections)

```toml
[environments.dev.connection]
type = "duckdb"
path = ":memory:"

[environments.dev.connections.analytics]
type = "snowflake"
database = "ANALYTICS_DB"
```

### Protected environments

```toml
[environments.prod]
protected = true
[environments.prod.connection]
type = "snowflake"
# ...
```

A protected environment is **never selected implicitly**. You must use `--env` explicitly:

```bash
t4t run ./my_project --env prod
```

Without `--env`, the default (`dev`) is used. If `dev` is not protected, it works without the flag.

### Naming strategy (optional overlay)

For shared-namespace scenarios (per-developer sandboxes, ephemeral CI schemas):

```toml
[environments.dev.naming]
schema_prefix = "dev_"
```

This prefixes the schema portion of all object names (e.g. `my_schema.my_table` → `dev_my_schema.my_table`). The primary environment separation mechanism is per-env connections (different `database`/`path` per environment).

## `pyproject.toml` (Python-package projects)

If your t4t project lives inside a Python package that already has a `pyproject.toml`, you can put t4t config under `[tool.t4t]`:

```toml
[tool.t4t.database]
type = "duckdb"
path = "data/my_project.duckdb"
```

Or use `[environments.*]` inside `pyproject.toml`:

```toml
[tool.t4t.environments.dev.connection]
type = "duckdb"
path = "data/dev.duckdb"
```

Note: when both `project.toml` and `pyproject.toml` exist in the same directory, `project.toml` takes precedence.
