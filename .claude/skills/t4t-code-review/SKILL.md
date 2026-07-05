---
name: t4t-code-review
description: Review a diff, branch, or PR of this repo following t4t's code review guidelines (correctness-first, verify-by-running, t4t danger zones). Use when asked to review code changes, a PR, or the working tree in this repository.
---

# t4t Code Review

Review the given target (a PR number/URL, a branch, or the current working
tree diff — default: `git diff main...HEAD` plus uncommitted changes)
following the repository's review guidelines.

## Procedure

1. **Read the guidelines first**: `docs/development/code-review.md`. They
   define the priority order (correctness → verify-by-running → t4t danger
   zones → tests-as-evidence → docs/claims) and the required output format.
   Do not review from memory of generic best practices — the danger-zone
   list is repo-specific.

2. **Run the mechanical gate** before reading code, and report its status:
   ```bash
   uv run ruff check t4t tests
   uv run ruff format --check t4t tests
   uv run pytest tests/ -m "not snowflake_e2e" --no-cov
   ```
   Do not report anything these tools already catch.

3. **Review per the guidelines**, with emphasis on:
   - changed lines: what input/state/dialect makes them wrong;
   - deleted lines: where the removed invariant is re-established;
   - changed signatures: grep for callers;
   - the t4t danger zones (SQL generation/escaping, adapter fallbacks,
     incremental state, OTS output, `ModelMetadata` ripple, Python policy).

4. **Verify by running** — execute the affected flow (e.g. `t4t run` /
   `t4t test` / `t4t compile` on `test_project/` or an example project),
   and run any documented commands the diff adds or changes, verbatim.
   State in the report exactly what was executed.

5. **Report** findings ranked most-severe first, each with `file:line`, a
   concrete failure scenario (required for correctness findings), the fix,
   and whether it blocks merge. Cap at the findings that matter. If asked
   to fix the findings, fix them after reporting and rerun step 2.
