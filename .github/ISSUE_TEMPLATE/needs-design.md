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

## Usage example — show it, get feedback, before designing further

Before writing the detailed design, draft a **concrete, realistic transcript**
of a developer using this feature: actual CLI invocations, actual config
snippets, actual (illustrative, hand-written — the feature doesn't exist yet)
output. Mark it clearly as proposed, not real output.

**Show this to the user directly and ask for usability feedback before
proceeding to Design decisions below.** This is a required conversation
checkpoint, not just documentation — it's far cheaper to change a command
name or an output format while it's three lines of prose than after
implementation, and the person who has to live with the UX daily is the
one who should react to it first.

If this issue is a foundational/library piece with no direct developer-
facing surface (e.g. #13's fingerprint computation, which is only exposed
indirectly through #14's selector), say so explicitly and point to which
downstream issue's usage example will demonstrate it end-to-end — don't
force an artificial CLI example onto a piece that doesn't have one.

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

## Implementation steps — an ordered path, not a task pile

A **numbered sequence**, not an unordered checklist. Each step names the
file(s) it touches, what it accomplishes, and how to verify *that step
alone* before moving to the next — infrastructure before logic, logic
before composition, composition before wiring, wiring before the final
E2E proof. The point is to make each step independently checkable, so an
implementing agent (or reviewer) can tell exactly where things went wrong
instead of discovering at the end that "everything's done" but the
feature doesn't work — the same failure mode the acceptance-criteria
section below exists to catch at the finish line, applied throughout.

The final step is always: run the acceptance-criteria E2E test.

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
