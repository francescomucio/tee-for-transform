---
name: Needs-design feature
about: A feature substantial enough to need a refinement pass before implementation
title: ""
labels: needs-design
---

<!--
This template exists because of a real, expensive lesson (2026-07, issues
#13/#14/#19/#30, PRs #71-#78): a "needs-design" label alone did not stop an
issue from going straight to implementation without the design actually
being settled. The result was six review rounds where component tests
passed and the feature was completely inert, because no boundary the
config crossed was checked end-to-end.

Every section below is required before this issue is assigned to an
implementing agent — not a nice-to-have, not something the implementer
fills in as they go. Delete this comment block once the issue is refined;
leave the section headers.
-->

## Why

What problem does this solve, and why now.

## Existing-state audit

Grep the codebase for anything that already implements or overlaps this
concept — including dead/duplicate implementations. (Two real examples:
a duplicate config-loading path in `cli/utils.py` vs `DatabaseConfigManager`,
and a fully dead `IncrementalStateManager` duplicating `StateManager` —
both found only by grepping before designing, not by reading the issue
that prompted the feature.)

```bash
grep -rn "<relevant term>" t4t/
```

## Prior art (if a comparable feature exists elsewhere)

If a similar feature exists in a tool your users are likely coming from
(dbt, SQLMesh, etc.), look it up via primary sources — docs, changelogs —
not memory. Two failure modes to check for specifically:
- **Naming collisions**: does reusing a term create a false expectation?
  (t4t's `state:modified` selector was renamed to `definition:changed`
  after research showed dbt's newer "dbt State" means something broader —
  keeping the old name would have promised behavior t4t doesn't have.)
- **Architecture mismatches**: does the reference tool's approach conflict
  with a decision t4t has already made? (SQLMesh's virtual/view-based
  environments were explicitly not adopted — they'd reopen the per-env-
  database decision in #30.)

## Design decisions (settled, not proposed)

Every "what happens when X" question resolved explicitly, with the
reasoning — not left for the implementer to infer. Common categories that
have bitten this project: behavior on missing/first-run state, behavior on
partial failure, how a new selector/flag combines with existing ones,
what's explicitly out of scope (write the non-goals down, don't just omit
them).

## Implementation constraints

Trace the actual code paths this feature will touch — real file:line
references, not a description of the feature in the abstract. This is
what catches gaps that only exist in the real codebase, not in how the
feature sounds when described (e.g. a fingerprinting feature that hashes
already-variable-substituted SQL, found only by tracing the actual
substitution call site and its timing relative to parsing).

## Acceptance criteria — the merge gate

A **concrete end-to-end test**, spelled out here (pseudocode is fine),
that exercises the real CLI/command path and checks real physical output —
not mocked internals. This is the single highest-leverage item in this
template: every review round of the naming saga this template is named
after had passing component tests and a completely inert feature, because
nothing ran the actual command and checked where the result landed.

Before finalizing: could this test pass in a broken state? (E.g. an
assertion on "did the command exit 0" is worthless if the command has a
pre-existing bug where it exits 0 on failure — check for that separately.)

## Non-goals

What this issue explicitly does not cover, and which other issue (if any)
owns it instead.
