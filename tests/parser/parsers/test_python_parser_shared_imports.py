"""Unit tests for #13 step 5's wiring into PythonParser.parse(): passing a
SharedImportTracker records project-local imports on
model_metadata["shared_import_files"].

Complements tests/parser/shared/test_import_tracking.py (which tests
SharedImportTracker in isolation) by proving PythonParser.parse() actually
uses it correctly, including the fixed-baseline behavior across two models
parsed in sequence (acceptance criterion 7).
"""

import sys
from pathlib import Path

import pytest

from t4t.parser.parsers.python_parser import PythonParser
from t4t.parser.shared.import_tracking import SharedImportTracker
from t4t.parser.shared.registry import ModelRegistry


@pytest.fixture(autouse=True)
def _cleanup_registries_and_sys_modules():
    modules_before = set(sys.modules.keys())
    path_before = list(sys.path)
    ModelRegistry.clear()
    yield
    ModelRegistry.clear()
    for name in set(sys.modules.keys()) - modules_before:
        del sys.modules[name]
    sys.path[:] = path_before


def _write_project(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    models_dir = tmp_path / "models"
    models_dir.mkdir()

    helper = models_dir / "shared_helper.py"
    helper.write_text("GREETING = 'hello'\n", encoding="utf-8")

    model_1 = models_dir / "model_1.py"
    model_1.write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, str(Path(__file__).parent))\n"
        "import shared_helper\n\n"
        "@model(table_name='model_1')\n"
        "def model_1():\n"
        "    return f\"SELECT '{shared_helper.GREETING}' AS greeting\"\n",
        encoding="utf-8",
    )
    model_2 = models_dir / "model_2.py"
    model_2.write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, str(Path(__file__).parent))\n"
        "import shared_helper\n\n"
        "@model(table_name='model_2')\n"
        "def model_2():\n"
        "    return f\"SELECT '{shared_helper.GREETING}' AS greeting\"\n",
        encoding="utf-8",
    )
    return tmp_path, helper, model_1, model_2


class TestPythonParserSharedImportWiring:
    def test_no_tracker_means_no_shared_import_files(self, tmp_path: Path) -> None:
        project_folder, _helper, model_1, _model_2 = _write_project(tmp_path)
        parser = PythonParser()
        models = parser.parse(model_1.read_text(encoding="utf-8"), file_path=model_1)
        assert models["model_1"]["model_metadata"]["shared_import_files"] == []

    def test_tracker_records_shared_helper_for_first_model(self, tmp_path: Path) -> None:
        project_folder, helper, model_1, _model_2 = _write_project(tmp_path)
        tracker = SharedImportTracker(project_folder)

        parser = PythonParser()
        models = parser.parse(
            model_1.read_text(encoding="utf-8"), file_path=model_1, import_tracker=tracker
        )

        shared = models["model_1"]["model_metadata"]["shared_import_files"]
        assert str(helper.resolve()) in shared

    def test_fixed_baseline_attributes_helper_to_second_model_too(self, tmp_path: Path) -> None:
        """Acceptance criterion 7's core proof: model_2 imports shared_helper
        *after* model_1 already cached it in sys.modules -- must still be
        attributed to model_2, proving a fixed (not per-model) baseline."""
        project_folder, helper, model_1, model_2 = _write_project(tmp_path)
        tracker = SharedImportTracker(project_folder)

        parser_1 = PythonParser()
        parser_1.parse(
            model_1.read_text(encoding="utf-8"), file_path=model_1, import_tracker=tracker
        )

        assert "shared_helper" in sys.modules  # sanity: genuinely cached now

        parser_2 = PythonParser()
        models_2 = parser_2.parse(
            model_2.read_text(encoding="utf-8"), file_path=model_2, import_tracker=tracker
        )

        shared_2 = models_2["model_2"]["model_metadata"]["shared_import_files"]
        assert str(helper.resolve()) in shared_2

    def test_own_file_excluded_from_shared_import_files(self, tmp_path: Path) -> None:
        project_folder, _helper, model_1, _model_2 = _write_project(tmp_path)
        tracker = SharedImportTracker(project_folder)

        parser = PythonParser()
        models = parser.parse(
            model_1.read_text(encoding="utf-8"), file_path=model_1, import_tracker=tracker
        )
        shared = models["model_1"]["model_metadata"]["shared_import_files"]
        assert str(model_1.resolve()) not in shared
