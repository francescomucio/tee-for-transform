# Adapters API

Database-specific adapters (DuckDB, Snowflake, PostgreSQL, BigQuery), registry, and shared base types.

## Status

Narrative API reference pages are not written yet. Adapters implement a common interface per backend.

## Where to look in code

| Area | Python package / module |
|------|-------------------------|
| Registry & public helpers | `t4t/adapters/__init__.py`, `t4t/adapters/registry.py` |
| Shared types & config | `t4t/adapters/base/core.py` (`AdapterConfig`, adapter base), `t4t/adapters/base/config.py` |
| DuckDB | `t4t/adapters/duckdb/` |
| Snowflake | `t4t/adapters/snowflake/` |
| PostgreSQL | `t4t/adapters/postgresql/` |
| BigQuery | `t4t/adapters/bigquery/` |

## User-facing docs

- [Database adapters](../../user-guide/database-adapters.md)
- [Configuration](../../getting-started/configuration.md)
- [CLI reference](../../user-guide/cli-reference.md)
