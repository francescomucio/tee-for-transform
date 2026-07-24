"""Detects project-local files a Python model imports as a side effect of
executing it (#13 constraint 7), via `sys.modules` diffing -- not static
`ast` parsing.

Parsing a Python model already `exec`s it (see `python_parser.py`'s
`_execute_python_file`); real imports triggered as a side effect land in
`sys.modules` and stay there. `SharedImportTracker` captures **one fixed
snapshot** of `sys.modules.keys()` before any model in the project is
parsed, then diffs against that same fixed baseline after each model's
exec.

The baseline must be fixed, not re-captured per model: if it were
per-model, a helper module already imported (and cached by Python) while
parsing an earlier model would look like nothing changed when a later model
imports the same, now-cached module -- so that later model would silently
miss the dependency. A fixed baseline avoids that false negative. The
accepted tradeoff (documented, not "fixed"): because the baseline never
advances during a single parsing run, a helper imported only by an earlier
model can also show up as "new" for a later model that doesn't actually
import it, over-attributing the later model's fingerprint to that helper.
This errs toward extra rebuilds rather than missed ones -- the same safe
direction other v1 fingerprint limitations take (see
docs/user-guide/fingerprinting.md).

The baseline is captured **once per process**, not once per
`SharedImportTracker` instance. A single `t4t run`/`build` invocation
parses the project's models more than once internally (lookup generation,
compilation, then again when saving analysis JSON -- each builds its own
`ParserOrchestrator`, each of which constructs its own tracker); if every
instance re-snapshotted `sys.modules.keys()` at construction time, only the
*first* pass in the process would see a clean baseline -- every later pass
would already have the shared helper cached from the first pass and treat
it as part of *its* baseline too, silently missing the dependency on every
pass after the first. A process-level baseline (reset only by tests, via
`reset_process_baseline_for_testing`) makes every pass within one `t4t`
invocation agree on what "before any model was parsed" means.
"""

import sys
from pathlib import Path

_process_baseline: frozenset[str] | None = None


def reset_process_baseline_for_testing() -> None:
    """Clear the process-level baseline cache.

    Test-only escape hatch: without this, tests that run multiple projects
    in the same process (e.g. via in-process CliRunner) would have later
    tests inherit an earlier test's baseline. Production code never needs to
    call this -- one real `t4t` invocation is one process.
    """
    global _process_baseline
    _process_baseline = None


class SharedImportTracker:
    """Detects newly-visible project-local files after each Python model's
    exec, diffed against a **process-level** fixed `sys.modules` baseline
    (see module docstring for why it's process-level rather than
    per-instance).

    One instance must be created **once per project-parsing pass**, before
    any Python model file is executed in that pass, and reused across all
    Python models parsed in it (see
    `ParserOrchestrator.discover_and_parse_models`).
    """

    def __init__(self, project_folder: str | Path) -> None:
        global _process_baseline
        self.project_folder = Path(project_folder).resolve()
        if _process_baseline is None:
            _process_baseline = frozenset(sys.modules.keys())
        self._baseline: frozenset[str] = _process_baseline

    def new_project_local_files(self, exclude: Path | None = None) -> list[Path]:
        """Project-local files present in `sys.modules` now but not in the
        fixed baseline, i.e. modules touched (directly or transitively) by
        Python model execution since this tracker was created.

        Filters to modules whose `__file__` resolves inside
        `project_folder` (excludes stdlib/site-packages/.venv) and,
        optionally, excludes one specific path (a model's own file).
        """
        current = set(sys.modules.keys())
        new_names = current - self._baseline

        exclude_resolved = exclude.resolve() if exclude is not None else None

        files: set[Path] = set()
        for name in new_names:
            module = sys.modules.get(name)
            if module is None:
                continue
            file_attr = getattr(module, "__file__", None)
            if not file_attr:
                continue
            try:
                resolved = Path(file_attr).resolve()
            except (OSError, ValueError):
                continue
            if exclude_resolved is not None and resolved == exclude_resolved:
                continue
            try:
                resolved.relative_to(self.project_folder)
            except ValueError:
                continue
            files.add(resolved)

        return sorted(files)
