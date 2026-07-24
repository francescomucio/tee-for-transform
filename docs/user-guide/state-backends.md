# State Backends

t4t persists two kinds of run state after every `t4t run`/`t4t build`:

- **Run manifests** -- what happened in a run (which models succeeded,
  failed, or were skipped), used by `--retry`.
- **Model [fingerprints](fingerprinting.md)** -- a stable hash of each
  model's definition, the foundation for future change-detection features
  (`definition:changed` selection, `t4t plan`, Slim CI).

Where that state lives is controlled per environment by
`environments.<env>.state.backend`, and is fully pluggable behind a single
`StateBackend` interface (`t4t/state/backend.py`). Two implementations exist
today: `"local"` (the default) and `"warehouse"`.

## `"local"` (default)

```toml
# No [environments.<env>.state] section needed -- this is the default.
```

State is written to local disk under the project's `output/` directory:
`output/<env>/last_run.json` and `output/<env>/runs.sqlite`. This is simple
and has no extra requirements, but it means state lives only on the machine
that ran `t4t` -- a fresh CI container, or a teammate running `t4t` from
their own machine, has no access to it. `--retry` and any future
`definition:changed` selection have no baseline to work from in that case.

## `"warehouse"`

```toml
[environments.prod.state]
backend = "warehouse"
```

State is written to the environment's own connection instead -- the same
`AdapterConfig`/connection the environment's models already use, no separate
credentials or infrastructure. This is what makes state usable from any
machine or CI runner that can connect to the warehouse, not just the one
that produced it.

### Layout: one state table per data schema

For every *data* schema a run touches (e.g. `analytics`, `staging`), t4t
auto-creates a paired `<schema>_STATE` schema containing a single shared
table, `t4t_model_state`:

```
$ t4t run myproject --env prod
Using state backend: warehouse
  analytics.* -> analytics_STATE.t4t_model_state
  staging.*   -> staging_STATE.t4t_model_state
```

`t4t_model_state` holds both run-manifest rows (one per run) and per-model
fingerprint rows (one per model per run), distinguished by a `record_type`
column (`'run'` or `'fingerprint'`) -- a `model_name` column distinguishes
which model a fingerprint row belongs to, the same "one table, many models"
shape `output/<env>/runs.sqlite`'s `fingerprints` table already uses
locally, extended into a paired warehouse schema rather than redesigned.

This is a **shared table per data schema**, not one state table per model
table: a schema with 50 models still gets exactly one
`<schema>_STATE.t4t_model_state`, not 50 separate state tables. Per-model
state tables were considered and rejected -- they would multiply
DDL/table-management cost forever for a benefit (per-table permissioning)
nobody asked for; schema-level permission alignment already satisfies the
actual goal of keeping state co-located with the data it describes.

Schema and table creation use `CREATE SCHEMA IF NOT EXISTS`/`CREATE TABLE IF
NOT EXISTS`, so this happens automatically on first use -- see
[Missing permissions](#missing-permissions-create-schemacreate-table) below
for what happens when the connection isn't allowed to create them.

### Run ordering: a database-native sequence, not a timestamp

Multiple CI runners or team members can write state concurrently, and clock
skew across machines makes a wall-clock "latest run" subtly wrong under
concurrent writes. To avoid that, "latest" is decided by a database-native
identity/sequence column (`ORDER BY id DESC`), not a timestamp -- except on
BigQuery, which has no such mechanism (see below). All writes are
`INSERT`-only (never updated in place), matching the append-only shape
`runs.sqlite` already uses locally.

The exact mechanism differs per adapter, because DuckDB's support turned out
to differ from the other two despite an initial assumption that all three
worked the same way:

| Adapter | Ordering mechanism |
| --- | --- |
| PostgreSQL | `id BIGINT GENERATED ALWAYS AS IDENTITY` |
| Snowflake | `id NUMBER GENERATED ALWAYS AS IDENTITY` |
| DuckDB | `CREATE SEQUENCE` + `id BIGINT DEFAULT nextval(...)` -- DuckDB does not support `GENERATED ALWAYS AS IDENTITY` (`Constraint not implemented`, confirmed directly against a real DuckDB connection) |
| BigQuery | **No ordering column.** See below. |

### BigQuery: known limitation, wall-clock ordering only

BigQuery has no native identity or sequence mechanism at all. The warehouse
backend falls back to a `written_at` timestamp column and orders by it
(`ORDER BY written_at DESC`) -- last-write-wins, with the same clock-skew
caveat under concurrent writers that the identity/sequence mechanism exists
to avoid on the other three adapters. This is a deliberate, documented v1
limitation, not something this feature attempts to solve further; revisit
only if it becomes a real problem in practice for BigQuery users running
concurrent/overlapping writers.

### Missing permissions (`CREATE SCHEMA`/`CREATE TABLE`)

Some warehouses run with locked-down service accounts that aren't granted
DDL rights. If the connection can't create the `<schema>_STATE` schema or
`t4t_model_state` table, t4t does **not** surface a raw permission-denied
stack trace. Instead, the run fails with an error that includes the exact
DDL an admin can run manually to grant a one-time head start, e.g.:

```
Could not create warehouse state schema/table for data schema 'analytics'
(...): permission denied for schema analytics_STATE.

Ask a database admin to run the following DDL manually, then re-run:

CREATE SCHEMA IF NOT EXISTS analytics_STATE

CREATE TABLE IF NOT EXISTS analytics_STATE.t4t_model_state (
    ...
)
```

If a run touches multiple data schemas and creation succeeds for some but
fails for others, the **whole run fails** -- t4t does not proceed with
state tracked for some models and not others. Partial state coverage is
worse than no coverage at all: a future `definition:changed` selector would
silently treat the untracked models as always-changed (or never-changed)
without any indication something was missed.

## Switching backends

Switching `backend` between `"local"` and `"warehouse"` (in either
direction) does **not** migrate any existing state. The first run under the
new backend simply has no baseline: any feature that depends on a stored
baseline (`--retry`, or a future `definition:changed` selector) fails open
-- it warns and treats every model as if it had never been run/fingerprinted
before, rather than crashing or misinterpreting the old backend's state.
This matches how a `fingerprint_spec_version` mismatch is already handled:
there's no way to convert one backend's state into the other's shape, so
t4t doesn't attempt to.

## What this does not cover

- **S3/GCS/standalone-Postgres-as-a-separate-service backends** -- not
  implemented. The warehouse backend is deliberately co-located with the
  environment's own connection, not a separate storage service.
- **Concurrent-writer stress testing.** The ordering-column mechanism is
  verified with sequential writes producing correctly-ordered rows; genuine
  concurrent-process races have not been tested. If a real race condition
  is observed in practice, that's a follow-up, not something this design
  assumes away.
- **State for secondary/named connections** (`environments.<env>.connections.*`).
  The warehouse backend tracks state only for models materialized via the
  environment's *primary* connection.
