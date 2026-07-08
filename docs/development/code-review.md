# Code Review Guidelines

The division of labor: **tools catch mechanical issues, review catches wrong
behavior.** Don't spend review attention on anything a linter can flag —
unused imports, modern syntax, complexity thresholds, magic numbers, import
order are ruff's job, enforced in CI, not checklist items. Review time goes
where judgment is required.

These guidelines are written to work for human and LLM reviewers alike.

**This document reviews diffs.** For refining a `needs-design` issue
*before* implementation starts, use `.github/ISSUE_TEMPLATE/needs-design.md`
and the `t4t-issue-refinement` skill instead — cheaper to catch a design gap
in an issue than after several PR rounds against inert code (see #13/#14/#30
and the PR #71-#75 history for why this distinction earned its own doc).

## Before review: let the tools run

```bash
uv run ruff check t4t tests        # lint (see [tool.ruff.lint] in pyproject.toml)
uv run ruff format --check t4t tests
uv run mypy t4t
uv run pytest tests/ -m "not snowflake_e2e" --no-cov
```

If these fail, fix them before asking for review. A review that reports
linter findings is wasted effort.

## 1. Correctness (blocking — always first)

For the **changed lines**: what input, state, timing, or dialect makes this
line wrong? Look for inverted conditions, off-by-one, `None` reaching an
attribute access, falsy-zero checks (`if value:` where `0` is valid),
copy-paste with the wrong variable, exceptions swallowed in `except` blocks.

For the **deleted lines**: name the invariant each one enforced, then find
where the new code re-establishes it. If you can't find it, that's a finding
— removed guards and narrowed validations are how regressions ship.

For **changed signatures and return shapes**: check the callers (`grep` the
symbol). A new parameter with a default, a changed return type, or a new
exception can break call sites that the diff never touches.

Every correctness finding must name a **concrete failure scenario**: the
input or state that triggers it and the wrong output or crash that results.
"This could be fragile" is not a finding.

## 2. Verify by running (the checklist can't save you here)

Claims are checked against reality, not against the diff:

- **Run the flow the change affects.** Not just the test suite — the actual
  command. If the change touches `t4t run`, run it on `test_project/` or an
  example project.
- **Execute documented commands verbatim.** If the change adds or edits
  docs, run every command block as written. A quickstart step that was never
  executed is a bug report from a future user.
- **Check the PR description against the code.** If it says "with fallback",
  find the fallback. If it says "all docs updated", grep for stragglers.

State in the review what you executed. "Suite green" and "I ran the
quickstart end-to-end" are different levels of evidence.

## 3. t4t danger zones (domain-specific)

- **SQL generation & dialects**: generated SQL must be valid on every
  supported backend, not just DuckDB. String escaping in generated SQL
  (quotes, identifiers) is a recurring bug source. If sqlglot transpilation
  is involved, check the output for at least one non-default dialect.
- **Silent adapter fallbacks**: the base adapter provides defaults (e.g.
  full rebuild instead of incremental). A change that works "everywhere" may
  be silently degrading on PostgreSQL/BigQuery. Warnings are not enough if
  the user never reads them — call out new fallback paths in the review.
- **Incremental state**: anything touching watermarks
  (`last_processed_value`), `sql_hash`/`config_hash`, or the run manifest
  must consider: first run, re-run after failure, schema change mid-stream,
  and state written by an older t4t version (`SCHEMA_VERSION` checks).
- **OTS output**: if the change affects the compiler/exporter, compile an
  example project and check the emitted OTS modules — they are the public
  contract, not an internal artifact.
- **`ModelMetadata` changes**: a new or changed metadata field must be
  handled consistently across parser → engine → OTS exporter → dbt importer,
  and documented. Grep for the field name; partial support is worse than none.
- **Python version policy**: t4t tracks the newest stable Python (currently
  3.14). Flag compatibility shims, version checks, and `from __future__`
  imports — they are dead weight under this policy.

## 4. Tests as evidence, not as presence

- Does the new test **fail on the pre-change code**? A regression test that
  passes either way proves nothing.
- Are the interesting cases covered — empty input, first run vs. subsequent
  run, the error path — or only the happy path?
- Do tests depend only on what's in the repository? No out-of-repo paths, no
  developer-machine state, no network unless explicitly marked
  (`snowflake_e2e`).
- Is anything asserted against generated files that tests themselves
  regenerate? (Churn in `examples/*/output/` is a smell.)

## 5. Docs and claims

- Do docs describe what the code **does now**, or what it will do someday?
  Aspirational features presented as existing are findings.
- Does user-facing behavior changed by this diff appear in the CHANGELOG?

## Review output format

Findings ranked most severe first, each with:

1. **Location**: `file:line`
2. **Failure scenario**: input/state → wrong result (required for
   correctness findings; for others, the concrete cost)
3. **Fix**: what to change
4. **Blocking?**: does this hold the merge, or is it a follow-up issue?

Cap the report at the findings that matter. Ten precise findings beat
thirty observations; if everything is worth mentioning, nothing is. What
was **executed** during the review is part of the report.

## Cadence

- Every PR: sections 1–5 above, scaled to the size of the change.
- Before a release: run the quickstart and one example project end-to-end
  on a clean environment; verify PyPI metadata matches `pyproject.toml`.
