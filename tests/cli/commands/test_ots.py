"""
Unit tests for OTS CLI commands.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest
import typer

from tee.cli.commands.ots import cmd_ots_run, cmd_ots_validate
from tee.parser.input import OTSModuleReaderError


def test_cmd_ots_validate_missing_path_raises(tmp_path: Path) -> None:
    with pytest.raises(typer.Exit) as exc:
        cmd_ots_validate(str(tmp_path / "missing.ots.json"))
    assert exc.value.exit_code == 1


def test_cmd_ots_validate_file_happy_path(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "module.ots.json"
    path.write_text("{}")

    class Reader:
        def read_module(self, _):
            return {"target": {"database": "db", "schema": "sch"}}

        def get_module_info(self, _):
            return {
                "module_name": "mod",
                "ots_version": "1.0",
                "transformation_count": 2,
                "target": {"database": "db", "schema": "sch"},
                "module_tags": ["tag1"],
                "has_test_library": True,
            }

    monkeypatch.setattr("tee.cli.commands.ots.OTSModuleReader", lambda: Reader())
    cmd_ots_validate(str(path))


def test_cmd_ots_validate_directory_empty(monkeypatch, tmp_path: Path) -> None:
    class Reader:
        def read_modules_from_directory(self, _):
            return {}

    monkeypatch.setattr("tee.cli.commands.ots.OTSModuleReader", lambda: Reader())
    cmd_ots_validate(str(tmp_path))


def test_cmd_ots_run_standalone_file_executes(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "module.ots.json"
    path.write_text("{}")

    models = {"fct_sales": {"model_metadata": {"table_name": "fct_sales"}}}
    functions = {"fn": {"name": "fn"}}

    monkeypatch.setattr("tee.cli.commands.ots.load_ots_modules", lambda _: (models, functions))

    class Reader:
        def read_module(self, _):
            return {"target": {"sql_dialect": "duckdb", "database": ":memory:", "schema": "main"}}

    class FakeParser:
        def __init__(self, *_args):
            self.parsed_models = {}

        def build_dependency_graph(self):
            return None

        def get_execution_order(self):
            return ["fct_sales"]

    class FakeModelExecutor:
        def __init__(self, *_args):
            self.execution_engine = SimpleNamespace(disconnect=lambda: None)

        def execute_models(self, **_kwargs):
            return {"executed_tables": ["main.fct_sales"], "failed_tables": []}

    class FakeTestExecutor:
        def __init__(self, _engine):
            pass

        def run_tests(self, _models, variables=None):
            return {"passed": 1, "failed": 0}

    monkeypatch.setattr("tee.cli.commands.ots.OTSModuleReader", lambda: Reader())
    monkeypatch.setattr("tee.cli.commands.ots.ProjectParser", FakeParser)
    monkeypatch.setattr("tee.engine.ModelExecutor", FakeModelExecutor)
    monkeypatch.setattr("tee.testing.TestExecutor", FakeTestExecutor)

    cmd_ots_run(str(path))


def test_cmd_ots_run_handles_reader_error(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "module.ots.json"
    path.write_text("{}")

    def _raise(_):
        raise OTSModuleReaderError("boom")

    monkeypatch.setattr("tee.cli.commands.ots.load_ots_modules", _raise)

    with pytest.raises(typer.Exit) as exc:
        cmd_ots_run(str(path))
    assert exc.value.exit_code == 1
