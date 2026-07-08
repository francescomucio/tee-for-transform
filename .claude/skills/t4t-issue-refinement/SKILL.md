---
name: t4t-issue-refinement
description: Refine a needs-design GitHub issue before it's handed to an implementing agent, following .github/ISSUE_TEMPLATE/needs-design.md. Use when asked to refine, scope, or prepare an issue for implementation in this repository, or when a "needs-design"-labeled issue is about to be assigned.
---

# t4t Issue Refinement

Refine the given issue (a number, URL, or "the issue we're discussing")
against `.github/ISSUE_TEMPLATE/needs-design.md` before it is considered
ready to hand to an implementing agent.

## Why this exists

Six PR rounds (#71-#75, 2026-07) shipped a feature that was completely
inert every time, despite green component tests, because the issue that
spawned it was never refined against real code before implementation
started. The fixes were found later, in review, at far higher cost than
finding them in the issue text would have been.

## Procedure

1. **Read `.github/ISSUE_TEMPLATE/needs-design.md` first.** Its section
   headers are the checklist; do not improvise a different structure.

2. **Existing-state audit — actually grep, don't assume.** Search the
   codebase for anything that already implements or overlaps the concept
   this issue introduces, including anything that looks abandoned or
   duplicated. Report what you find even if it means the issue's premise
   needs to change.

3. **Prior art, via primary sources.** If a comparable feature exists in a
   tool this project's users likely know (dbt, SQLMesh, etc.), fetch the
   actual current docs — don't rely on training-data memory, especially
   for anything that may have shipped after your knowledge cutoff. Check
   specifically for naming collisions (would reusing a term promise
   behavior this project doesn't have?) and architecture mismatches
   (does the reference tool's approach conflict with a decision this
   project already made?).

4. **Draft a usage example and show it to the user before going further —
   this is a conversation checkpoint, not a documentation step you do
   silently.** Write a concrete, realistic transcript: actual CLI
   invocations, actual config, actual (hand-written, clearly-marked-
   illustrative) output. Present it in your response and explicitly ask
   whether it matches what they'd expect to type and see. Don't proceed to
   settling the detailed design until you've done this — a command name or
   output format is far cheaper to change right now than after
   implementation, and the person who'll use this daily should react to
   it first. If the issue has no direct developer-facing surface (a
   foundational/library piece), say so and name which downstream issue's
   usage example covers it instead — don't force one.

5. **Trace real code paths.** For every mechanism the issue proposes,
   find the actual file:line in the current codebase it will touch or
   replace. A design that only exists in prose, never checked against
   what the code actually does, is how timing bugs and missing-case bugs
   (e.g. a fingerprinting feature hashing post-substitution text because
   nobody traced when substitution actually runs) get shipped.

6. **Settle every "what happens when X" explicitly.** Missing state,
   partial failure, combination with existing flags/selectors, explicit
   non-goals — write the answer into the issue, don't leave it for the
   implementer's judgment. If you're not sure, that uncertainty itself is
   a finding to report, not something to paper over with vague language.

7. **Write the acceptance criteria as a real end-to-end test**, exercising
   the actual CLI/command path against real (or fixture) state, not mocked
   internals. Then adversarially check the test itself: could it pass in a
   broken state? (A "command exits 0" assertion is worthless if the
   command has a separate bug where it always exits 0.)

8. **Write the implementation steps as a numbered, ordered sequence, not
   a task pile.** Each step names the file(s) it touches, what it
   accomplishes, and how to verify that step alone before moving to the
   next — infrastructure before logic, logic before composition,
   composition before wiring, wiring before the final E2E proof. This
   gives the implementing agent (and whoever reviews the PR) a way to
   find exactly where things diverged, instead of discovering only at the
   end that nothing actually works end to end. Last step is always: run
   the acceptance-criteria test from the previous step.

9. **Second pass on your own fix.** Before presenting a proposed fix as
   settled, try to state it as an exact mechanism — file, line, function.
   If you can't, you haven't verified it yet; go trace it for real. This
   step alone caught a fix that was both riskier than necessary and
   silently missing an entire code path, on an issue that had already
   been through one refinement round.

10. **If refining an already-open issue**, edit the issue body directly
    (don't just comment) so a reader gets the complete, current design in
    one place — but note what changed and why, either in the edit itself
    or a short comment, so the history stays legible.

## Output

A refined issue body following the template's structure, plus a short
summary to the user: what was added/changed, and — critically — what
existing bug, duplicate code, or gap the refinement surfaced that they
should know about even if it doesn't block this specific issue.
