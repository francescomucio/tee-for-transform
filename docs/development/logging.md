# Structured logging (`--log-format`)

t4t's `run`/`build`/`test` commands accept `--log-format text|json` (default
`text`) and the `T4T_LOG_FORMAT` environment variable (same values). Both
render the same underlying `logging` records — see
`t4t/observability/logging_setup.py` for the implementation and
`docs/development/contributing.md`'s Code Style section for the "always use
`logging`, never raw `print()`" convention this depends on.

## Text mode (default)

Byte-compatible with t4t's historical `print()`/`typer.echo()` output, plus
genuinely live per-model/per-test progress lines that did not exist before
([issue #36](https://github.com/francescomucio/tee-for-transform/issues/36)):

```
$ t4t run myproject --env prod
Running t4t on project: myproject
Refreshing generated lookup models...
  ▶ models/staging/stg_orders.sql
  ✅ models/staging/stg_orders.sql (0.8s, 12,043 rows)
  ▶ models/marts/fct_orders.sql
  ✅ models/marts/fct_orders.sql (2.1s, 340,221 rows)
Completed! Successfully executed: 2 tables
```

## JSON mode

One JSON object per stdout line (JSONL) — flat, no nested envelope. Every
line has `ts`/`level`/`msg`. Lines for the six *named lifecycle events*
additionally carry a `type` field plus their own event-specific fields, all
at the top level (no `.data.x` nesting):

```
$ t4t run myproject --env prod --log-format json | jq -c 'select(.type=="model_finished")'
{"ts":"2026-07-23T09:14:03.925Z","level":"info","type":"model_finished","run_id":"3f2a1e4c-...","msg":"  ✅ models/staging/stg_orders.sql (0.8s, 12,043 rows)","model":"models/staging/stg_orders.sql","status":"success","duration_ms":812,"row_count":12043,"materialization":"incremental","error":null}
```

A generic diagnostic message (not one of the six named events) still renders
as valid JSON — `ts`/`level`/`msg` are always present — just without a
`type` field:

```json
{"ts": "2026-07-23T09:14:01.998Z", "level": "info", "msg": "Refreshing generated lookup models..."}
```

**Only the six named events below have a documented, stable schema.** Every
other message is guaranteed to be valid JSON with `ts`/`level`/`msg`, but its
exact wording and any additional fields are not part of a stable contract —
don't build tooling that pattern-matches on non-`type`d `msg` text.

## The six named lifecycle events

| `type`           | Emitted from                                                        | When |
|-------------------|----------------------------------------------------------------------|------|
| `run_started`     | `t4t/cli/commands/run.py`, `build.py`, `test.py`                     | First line of the invocation |
| `model_started`   | `t4t/engine/executors/model_executor.py` (`ModelExecutor.execute()`) | Immediately before a model executes |
| `model_finished`  | same                                                                  | Immediately after a model finishes (success or failure) |
| `test_started`    | `t4t/testing/executors/model_test_executor.py` / `function_test_executor.py` | Before a model's/function's tests run |
| `test_finished`   | same                                                                  | After a model's/function's tests finish |
| `run_finished`    | `t4t/cli/commands/run.py` / `build.py` / `test.py`                   | Last line of the invocation |

Every event carries `run_id` — the same value across the whole invocation's
event stream *and* the row appended to `.t4t/output/<env>/runs.sqlite` for
that run (the join key: `select run_id from runs order by rowid desc limit 1`).

### `run_started`

| Field | Type | Notes |
|---|---|---|
| `run_id` | string (UUID) | Generated once, at the very start of the CLI command. |
| `env` | string | Resolved environment name (e.g. `dev`, `prod`). |
| `t4t_version` | string | |
| `selection` | list[string] \| null | `--select` patterns, if any. |

### `model_started`

| Field | Type |
|---|---|
| `run_id` | string |
| `model` | string — fully-qualified table name |

### `model_finished`

| Field | Type | Notes |
|---|---|---|
| `run_id` | string | |
| `model` | string | |
| `status` | `"success"` \| `"failed"` | |
| `duration_ms` | int | Real per-model wall-clock time. |
| `row_count` | int \| null | Null on failure or when unavailable. |
| `materialization` | string \| null | `"table"`, `"view"`, `"incremental"`, etc. |
| `error` | string \| null | Set when `status == "failed"`. |

### `test_started` / `test_finished`

Same shape as `model_started`/`model_finished`, keyed by `model` (or
`function` for function-level tests), plus on `test_finished`: `status`,
`duration_ms`, `total`, `passed`, `failed`.

### `run_finished`

| Field | Type | Notes |
|---|---|---|
| `run_id` | string | |
| `status` | `"success"` \| `"failed"` \| `"warning"` \| `"error"` | `"error"` means the run raised before completing normally; `"warning"` is `t4t test`-specific (tests passed but produced warnings). |
| `duration_ms` | int | `run`/`build` only. |
| `executed_tables` / `failed_tables` | int | `run`/`build` only, present on the normal-completion path. |

## Tracebacks on crash

When a log record carries `exc_info` (i.e. was logged from an `except`
block via `logger.exception(...)`/`logger.error(..., exc_info=True)`), the
two formatters render it differently, consistent with how each mode treats
everything else:

- **Text mode**: the formatted traceback is inlined into the same line's
  message text (`msg\n<traceback>`), matching historical
  `print()`/`traceback.print_exc()` output.
- **JSON mode**: the formatted traceback is emitted as its own top-level
  `exc_info` string field on that line's JSON object, keeping `msg` itself
  free of embedded newlines/traceback text — the payload stays one valid
  JSON object per line either way.

See `TextFormatter.format()` / `JSONFormatter.format()` in
`t4t/observability/logging_setup.py`.

## Redaction

`--log-format json` redacts secret values (currently: any dict-valued
`extra` field's `password` key) before serializing — this is enforced once,
centrally, in `JSONFormatter`, not at each call site. See
`docs/development/contributing.md`'s Code Style section for why call sites
must pass structured config via `extra={...}` rather than interpolating it
into the message string (redaction never sees the rendered `msg`).
