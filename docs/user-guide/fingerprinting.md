# Model Fingerprinting

Every time you run `t4t run` or `t4t build`, t4t computes and stores a
**definition fingerprint** for each model it attempts. A fingerprint is a
stable hash of a model's *definition* -- its own source plus, transitively,
the definitions of everything it depends on -- independent of whether the
model's last run actually succeeded.

This is a foundational, storage-only feature: t4t does not yet act on
fingerprints itself (that's `definition:changed` selection, a separate,
upcoming feature). Today, fingerprinting exists so that feature -- and
future ones like `t4t plan` and Slim CI -- can be built on a single, shared
notion of "did this model's definition change" without re-solving change
detection each time.

## What gets hashed

For every model, t4t stores three separate values:

- **`sql_hash`** -- a hash of the model's own source (SQL query or Python
  function), read directly from its source file.
- **`config_hash`** -- a hash of the model's config/materialization metadata
  (materialization type, incremental strategy, schema, tests, etc).
- **`fingerprint`** -- the two values above combined with the fingerprints
  of the model's *direct* upstream dependencies, Merkle-style:

  ```
  fingerprint(model) = hash(sql_hash, config_hash, [fingerprint(dep) for dep in direct upstream deps])
  ```

  Because each model's fingerprint already folds in its own dependencies'
  fingerprints, a change anywhere upstream propagates through the whole
  chain automatically -- t4t doesn't need to re-hash the entire dependency
  graph every time one model changes.

Keeping `sql_hash` and `config_hash` separate (rather than folding
everything into one opaque value) matters for future consumers: a tool
reporting *why* a model is considered changed needs to distinguish "the
query logic changed" from "only the materialization config changed" from
"nothing here changed, but something upstream did."

### SQL hashing is comment- and whitespace-insensitive

`sql_hash` is computed from the model's **canonical AST**, not its raw
text: t4t parses the SQL with sqlglot and re-serializes it in a normalized
form before hashing. This means:

- Reformatting a query (extra whitespace, different indentation) does not
  change `sql_hash`.
- Adding, editing, or removing a comment does not change `sql_hash`.
- Any change to the actual query logic does change `sql_hash`.

### Python models

For Python models, `sql_hash` is a hash of the model's entire source file,
read from disk the same way as SQL models.

### Variables (`--vars`) never affect the fingerprint

t4t always hashes the source file as written on disk -- never the
`--vars`-substituted SQL used at execution time. Running the same,
unchanged model with different `--vars` values produces the same
`sql_hash` and `fingerprint` every time.

## Where fingerprints are stored

Fingerprints are persisted through the same `StateBackend` used for run
manifests (`t4t/state/backend.py`), scoped per environment the same way:
`output/<env>/runs.sqlite`, in a `fingerprints` table alongside the existing
`runs` table. After each run, t4t writes `sql_hash`/`config_hash`/
`fingerprint` for every model that was *attempted* (selected and execution
was attempted) that run, regardless of whether that particular model's
execution succeeded or failed.

Each stored record also carries a `fingerprint_spec_version`. If the
algorithm or its inputs change in a future t4t release, that version is
bumped. A stored fingerprint whose version doesn't match the current tool's
is **not** migrated -- it's treated the same as having no stored baseline
at all (fail open), since there is no way to convert an older hash into the
current algorithm's output.

## Known v1 limitations

These are documented, intentional scope boundaries for the first version of
fingerprinting -- not bugs, and not currently planned to be "fixed" without
a specific need driving it:

### `SELECT *` models are fingerprinted at the whole-query level

t4t cannot currently determine, from a `SELECT *` query alone, which
*columns* actually changed without querying the upstream schema. A `SELECT
*` model's fingerprint still correctly reflects changes to its own query
text and its dependencies' fingerprints -- it's just coarser than
column-level lineage would allow. This is the same limitation other tools
with comparable "definition fingerprint" concepts (e.g. dbt State) have;
resolving it fully depends on column-lineage work that's a larger,
separate effort.

### One Python file, multiple models: whole-file hashing

A single Python file can define more than one model (via multiple
`@model`-decorated functions, or a loop that generates several models).
`sql_hash` for a Python model is a hash of that model's *entire source
file* -- so editing any one model (or even unrelated code) in a file that
defines several models marks all of them as changed, not just the one that
actually moved. Precise per-function hashing is a natural follow-up once
the coarser, whole-file version has been proven in practice.

### Shared-import detection is Python-only

Python models sometimes `import` a shared, non-model helper file (e.g. a
`utils.py` with logic reused across several models). t4t detects this by
diffing `sys.modules` before and after each Python model's execution, and
folds the content hash of any newly-visible project-local file into that
model's fingerprint -- so editing a shared helper does correctly change the
fingerprint of every Python model that imports it (directly or
transitively), without needing to statically parse `import` statements.

This detection mechanism does not apply to SQL models or to SQL/Python
functions: SQL models can only reference other models or functions
(already tracked as dependency-graph edges, and therefore already covered
by the hash chain), so there is no equivalent "shared file" gap to close
for them.

One further consequence of the detection approach worth knowing: the
`sys.modules` baseline is fixed once per `t4t` invocation (not
re-captured per model), which is required so that a helper already
imported by an earlier model is still correctly attributed to a later
model that imports the same, now-cached module. The tradeoff is that a
helper imported by *any* Python model earlier in the same run can, in
principle, also be over-attributed to a later Python model that doesn't
actually import it. This errs toward occasionally over-including a model
as "changed" rather than ever missing a real change -- the same safe
direction the other limitations above take.

### A skipped upstream dependency leaves a silent gap in the hash chain

`compute_project_fingerprints` walks the project in topological
(dependency) order and, for each model, folds in the *already-computed*
fingerprints of its direct upstream dependencies. If a direct dependency
was never hashed in that pass -- because it was skipped by selection, or
because hashing it failed (see the `FingerprintError` handling above) --
that dependency simply contributes nothing to the downstream model's hash
chain. The downstream model still gets a valid `fingerprint`; it is just
**incomplete**, missing that one dependency's contribution.

This can happen, concretely, in two situations:

- Running `t4t run` with a selector that excludes an upstream model, so it
  is never attempted (and therefore never fingerprinted) in that
  invocation.
- An upstream model's own source becoming unreadable or unparseable for a
  run (triggering `FingerprintError`), so it is skipped and logged with a
  warning, but downstream models still get fingerprinted around the gap.

The practical consequence for future consumers -- most notably #14's
`definition:changed` selector -- is this: **a model's `fingerprint` may not
change on some run even though an upstream dependency that was skipped in
a *previous* run has, in the meantime, actually changed.** The chain only
ever reflects dependencies that were actually hashed *in the same pass*
that produced the stored fingerprint; a dependency's change can't
propagate downstream until both it and everything between it and the
downstream model are hashed together in the same run.

This is a known, accepted v1 behavior, not a bug: fixing it properly would
mean either always fingerprinting the full project graph regardless of
selection (defeating the point of selective runs) or persisting and
reusing prior fingerprints for un-attempted dependencies mid-computation
(a real design change, not something to bolt on quietly). Like the other
limitations in this section, it errs toward a merely incomplete signal
rather than a wrong one -- the fingerprint that *is* produced is still a
valid, stable hash of exactly what was actually hashed that run.
