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
"""

import sys
from pathlib import Path


class SharedImportTracker:
    """Captures a fixed `sys.modules` baseline and detects newly-visible
    project-local files after each Python model's exec.

    One instance must be created **once per project-parsing run**, before
    any Python model file is executed, and reused across all Python models
    parsed in that run (see `ParserOrchestrator.discover_and_parse_models`).
    """

    def __init__(self, project_folder: str | Path) -> None:
        self.project_folder = Path(project_folder).resolve()
        self._baseline: frozenset[str] = frozenset(sys.modules.keys())

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
