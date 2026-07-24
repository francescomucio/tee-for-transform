"""Unit tests for #13 step 5: SharedImportTracker.

Uses real `sys.modules`/`import` machinery (not mocked) to prove the fixed-
baseline diff actually works the way constraint 7 requires: a helper module
already imported (and cached) while an earlier model was parsed must still
be attributed to a later model that imports the same, now-cached module.
python_parser.py's own wiring is tested separately in
tests/parser/parsers/test_python_parser_shared_imports.py.
"""

import sys
from pathlib import Path

import pytest

from t4t.parser.shared.import_tracking import (
    SharedImportTracker,
    reset_process_baseline_for_testing,
)


@pytest.fixture(autouse=True)
def _cleanup_sys_modules_and_path():
    """Every test here mutates real sys.modules/sys.path via `import` --
    restore both afterward so this test file can't leak state into other
    tests in the same process. Also resets the process-level baseline cache
    (see import_tracking.py's module docstring for why it's process-level)
    so each test gets its own clean baseline, matching production's "one
    process per run" reality."""
    reset_process_baseline_for_testing()
    modules_before = set(sys.modules.keys())
    path_before = list(sys.path)
    yield
    for name in set(sys.modules.keys()) - modules_before:
        del sys.modules[name]
    sys.path[:] = path_before
    reset_process_baseline_for_testing()


def _write_project(tmp_path: Path) -> tuple[Path, Path, Path]:
    """project_folder/models/{model_a.py, model_b.py, shared_helper.py}"""
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    helper = models_dir / "shared_helper.py"
    helper.write_text("GREETING = 'hello'\n", encoding="utf-8")
    model_a = models_dir / "model_a.py"
    model_a.write_text("# model a\n", encoding="utf-8")
    model_b = models_dir / "model_b.py"
    model_b.write_text("# model b\n", encoding="utf-8")
    return tmp_path, model_a, model_b


def _real_import(module_name: str, search_dir: Path) -> None:
    """Mimic what executing a Python model file that does `import <module_name>`
    (after inserting its own directory onto sys.path) would trigger --
    genuinely populates sys.modules via Python's real import machinery."""
    sys.path.insert(0, str(search_dir))
    __import__(module_name)


class TestSharedImportTracker:
    def test_new_project_local_files_empty_before_any_import(self, tmp_path: Path) -> None:
        project_folder, _, _ = _write_project(tmp_path)
        tracker = SharedImportTracker(project_folder)
        assert tracker.new_project_local_files() == []

    def test_detects_newly_imported_project_local_file(self, tmp_path: Path) -> None:
        project_folder, model_a, _ = _write_project(tmp_path)
        tracker = SharedImportTracker(project_folder)

        _real_import("shared_helper", project_folder / "models")

        found = tracker.new_project_local_files(exclude=model_a)
        assert (project_folder / "models" / "shared_helper.py").resolve() in found

    def test_excludes_stdlib_and_outside_project(self, tmp_path: Path) -> None:
        project_folder, model_a, _ = _write_project(tmp_path)
        tracker = SharedImportTracker(project_folder)

        # Import something real but definitely not project-local.
        _real_import("json", project_folder / "models")  # already stdlib, cached or not

        found = tracker.new_project_local_files(exclude=model_a)
        assert found == []

    def test_exclude_omits_the_models_own_file(self, tmp_path: Path) -> None:
        project_folder, model_a, _ = _write_project(tmp_path)
        tracker = SharedImportTracker(project_folder)

        # Simulate model_a itself being loaded as a real module (as if it were
        # imported rather than exec'd) -- excluding it should hide it even
        # though it resolves inside the project directory.
        _real_import("model_a", project_folder / "models")

        found = tracker.new_project_local_files(exclude=model_a)
        assert model_a.resolve() not in found

    def test_fixed_baseline_attributes_cached_import_to_second_model(self, tmp_path: Path) -> None:
        """The exact scenario in acceptance criterion 7: model B imports the
        same helper model A already imported (now cached) -- a fixed
        baseline must still attribute the helper to model B."""
        project_folder, model_a, model_b = _write_project(tmp_path)
        tracker = SharedImportTracker(project_folder)

        # Model A's "exec" imports the helper for the first time.
        _real_import("shared_helper", project_folder / "models")
        found_a = tracker.new_project_local_files(exclude=model_a)
        helper_path = (project_folder / "models" / "shared_helper.py").resolve()
        assert helper_path in found_a

        # Model B's "exec" imports the same, now-cached helper. A per-model
        # (non-fixed) baseline would see nothing new here and miss it.
        assert "shared_helper" in sys.modules  # sanity: genuinely cached
        found_b = tracker.new_project_local_files(exclude=model_b)
        assert helper_path in found_b

    def test_module_without_file_attribute_is_skipped(self, tmp_path: Path) -> None:
        project_folder, model_a, _ = _write_project(tmp_path)
        tracker = SharedImportTracker(project_folder)

        import types

        fake = types.ModuleType("fake_no_file_module")
        sys.modules["fake_no_file_module"] = fake
        try:
            found = tracker.new_project_local_files(exclude=model_a)
            assert found == []
        finally:
            del sys.modules["fake_no_file_module"]
