# Model Selection

`t4t run`, `t4t build`, and `t4t test` all accept `-s`/`--select` and
`-e`/`--exclude` to run a subset of your project instead of everything.
This page covers the full selection language: name patterns, tags,
**definition state** (`definition:changed`), **run state**
(`run:failed`/`--retry`), graph modifiers, and how multiple selectors
combine.

Name patterns and `tag:` work identically on every command that accepts
`--select`. `definition:changed`, `run:failed`, and graph modifiers (`+`)
need a persisted run/fingerprint baseline and the project's dependency
graph, which today are wired up for `t4t run`/`t4t build` only.

## Quick reference

| Selector | Meaning |
|---|---|
| `my_model` | Exact name or glob pattern (`*`, `?`) |
| `tag:nightly` | Models carrying the `nightly` tag |
| `definition:changed` | Models whose definition changed vs. the stored baseline (see [Fingerprinting](fingerprinting.md)) |
| `run:failed` | Models with `status == "failed"` in the last persisted run |
| `+my_model` | `my_model` and everything it depends on (**upstream**) |
| `my_model+` | `my_model` and everything that depends on it (**downstream**) |
| `+my_model+` | Both directions at once |
| `--select a --select b` | **Union** (OR): matches `a` **or** `b` |
| `--select "a,b"` | **Intersection** (AND, comma, no spaces): matches `a` **and** `b` |

`--retry` (on `run`/`build`) is sugar for `--select run:failed+`.

## Name patterns and tags

These predate `definition:`/`run:` and work exactly as before:

```bash
t4t run ./my_project --select my_model
t4t run ./my_project --select "staging_*"
t4t run ./my_project --select tag:nightly
```

A name pattern matches the model's full qualified name (`schema.table`) or
just the table part, case-insensitively, with `fnmatch`-style wildcards.

Tags currently require a Python model (`@model(tags=[...])`); SQL models'
`-- metadata: {...}` comment block does not carry `tags` through in the
current parser.

## `definition:changed`

Selects models whose current **definition fingerprint** differs from the
fingerprint stored the last time that model was attempted (see
[Fingerprinting](fingerprinting.md) for exactly what's hashed: a model's own
SQL/config plus, transitively, everything it depends on).

```bash
$ t4t run myproject --select definition:changed+
Filtered to 3 models (from 40 total)
Filtered execution order: stg_orders -> fct_orders -> customer_ltv
```

Because the fingerprint chain includes upstream dependencies, a model can
show as "changed" either because its own source moved, or because
something it depends on did — `definition:changed` catches both without
needing `+`. The `+` modifier is for explicitly pulling in *downstream*
dependents that haven't themselves changed, so they get rebuilt on top of
the new upstream data.

### No baseline yet (first run)

If a model has never had a fingerprint stored for the current environment,
it's treated as changed (fail-open) rather than silently skipped:

```bash
$ t4t run myproject --select definition:changed
No baseline (env: dev) for 40 model(s) -- treating as changed: ...
Filtered to 40 models (from 40 total)
```

This is deliberate: the alternative (select nothing) risks silently
skipping models a user expects to run on their very first invocation.

### Baseline update semantics

A model's stored fingerprint updates whenever it is **selected and
execution is attempted** in a run whose manifest gets persisted —
regardless of whether that attempt **succeeded or failed**. A model that
fails for a transient reason (e.g. a warehouse timeout) does not keep
showing up under `definition:changed` on every subsequent run just because
it failed; use `run:failed` (below) for "retry the broken one," which is
deliberately a separate, orthogonal selector. Models that were **not**
attempted (excluded via `--exclude`, or skipped because an upstream
dependency failed) do not get their baseline updated.

## `run:failed`

Selects models with `status == "failed"` in the most recently persisted run
manifest for the current environment (`output/<env>/last_run.json`):

```bash
t4t run myproject --select run:failed
```

If there is no previous run manifest, or nothing failed in it,
`run:failed` matches nothing (with a warning), the same "no models matched"
outcome as any other selector matching zero models.

### `--retry`

```bash
$ t4t run myproject --retry
Filtered to 2 models (from 40 total)
Filtered execution order: fct_orders -> customer_ltv
```

`--retry` is sugar for `--select run:failed+` — one implementation, not a
separate mechanism. It cannot be combined with an explicit `--select`.

## Graph modifiers

A leading `+` expands **upstream** (parents/ancestors); a trailing `+`
expands **downstream** (children/dependents). Modifiers apply to the
*whole* selector value, not to an individual comma-separated token inside
it (see [Combining selectors](#combining-selectors) below) — they are
stripped off first, the remainder is evaluated, and the modifier expands
*that result*.

| Pattern | Meaning |
|---|---|
| `+definition:changed` | Upstream of every changed model |
| `definition:changed+` | Downstream of every changed model |
| `run:failed` | Only models that failed last run |
| `run:failed+` | Failed models + their downstream (what `--retry` uses) |
| `+run:failed` | Upstream of failed models |
| `+my_model+` | Both directions at once |

Modifiers work the same way for `t4t run`, `t4t build`, and combined with
`definition:`/`run:` or a comma AND-group -- e.g.
`"definition:changed,tag:nightly+"` first computes the changed-and-nightly
intersection, *then* expands downstream from that result.

## Combining selectors

t4t implements **dbt's own selector-combination algebra exactly** — this is
deliberate parity, not a superficial similarity, so if you already know
dbt's `--select` syntax, it works the same way in t4t:

- **Space (repeated `--select`) = union (OR).** A model is selected if it
  matches *any* of the values you passed:

  ```bash
  # union: matches the changed model(s) OR anything tagged nightly
  t4t run myproject --select definition:changed --select tag:nightly
  ```

- **Comma within *one* `--select` value (no spaces) = intersection (AND).**
  A model must satisfy *every* comma-separated condition:

  ```bash
  # intersection: only models that are both changed AND tagged nightly
  t4t run myproject --select "definition:changed,tag:nightly"
  ```

Intersection works uniformly across every selector type — name patterns,
`tag:`, `definition:`, `run:` — you can mix them freely inside one
comma-group: `--select "definition:changed,tag:nightly,my_model*"`.

Formally: each `--select`/`--exclude` value parses into one **AND-group**
of atomic conditions (its comma-separated tokens); the set of values from
repeated flags **OR**s across those groups. A single, no-comma value (e.g.
`--select my_model`) is the degenerate one-condition case of the same
structure — today's plain name/tag selection is unchanged.

## `--exclude`

`--exclude` uses the same syntax as `--select` (name patterns, tags,
`definition:`/`run:`, comma/space algebra, and graph modifiers) and is
applied *after* selection: a model matching `--select` is dropped if it
also matches `--exclude`.

## Reserved prefixes

`tag:`, `definition:`, `run:`, and `data:` (reserved for future
data-freshness selection, not implemented yet) are reserved namespaces —
avoid naming a model so that its name starts with one of these prefixes
followed by a colon, as it would be parsed as a virtual selector instead of
a name pattern.

## Not yet implemented

- **`data:changed`** ("data state" — definition change *or* upstream data
  went stale) is a deliberately separate, broader concept from
  `definition:changed`, tracked for a future release.
- **Remote/shared baselines** (e.g. comparing against a CI/main branch's
  last successful run) — today's baseline is always the local
  environment's own last attempt.
