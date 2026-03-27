# Adapters API

Database-specific adapters (DuckDB, Snowflake, PostgreSQL, BigQuery), registry, and shared base types.

## Status

Narrative API reference pages are not written yet. Adapters implement a common interface per backend.

## Where to look in code

| Area | Python package / module |
|------|-------------------------|
| Registry & public helpers | `tee/adapters/__init__.py`, `tee/adapters/registry.py` |
| Shared types & config | `tee/adapters/base/core.py` (`AdapterConfig`, adapter base), `tee/adapters/base/config.py` |
| DuckDB | `tee/adapters/duckdb/` |
| Snowflake | `tee/adapters/snowflake/` |
| PostgreSQL | `tee/adapters/postgresql/` |
| BigQuery | `tee/adapters/bigquery/` |

## User-facing docs

- [Database adapters](../../user-guide/database-adapters.md)
- [Configuration](../../getting-started/configuration.md)
- [CLI reference](../../user-guide/cli-reference.md)
