"""
Coverage tests for legacy import command module.
"""

from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import pytest
import typer

legacy_import_module = import_module("tee.cli.commands.import")
cmd_import = legacy_import_module.cmd_import


def test_cmd_import_legacy_fails_for_missing_source(tmp_path: Path) -> None:
    with pytest.raises(typer.Exit) as exc:
        cmd_import(
            source_project_folder=str(tmp_path / "missing"),
            target_project_folder=str(tmp_path / "target"),
        )
    assert exc.value.exit_code == 1


def test_cmd_import_legacy_dry_run_unknown_project_type(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    target = tmp_path / "target"

    project_type = SimpleNamespace(UNKNOWN=SimpleNamespace(value="unknown"))
    monkeypatch.setattr(
        "tee.importer.detector.ProjectType",
        project_type,
        raising=True,
    )
    monkeypatch.setattr(
        "tee.importer.detector.detect_project_type",
        lambda _: project_type.UNKNOWN,
        raising=True,
    )

    with pytest.raises(typer.Exit) as exc:
        cmd_import(str(source), str(target), dry_run=True)
    assert exc.value.exit_code == 1


def test_cmd_import_legacy_calls_dbt_importer(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    target = tmp_path / "target"
    called: dict[str, object] = {}

    project_type = SimpleNamespace(
        DBT=SimpleNamespace(value="dbt"),
        UNKNOWN=SimpleNamespace(value="unknown"),
    )

    def _fake_import_dbt_project(**kwargs):
        called.update(kwargs)

    monkeypatch.setattr("tee.importer.detector.ProjectType", project_type, raising=True)
    monkeypatch.setattr(
        "tee.importer.detector.detect_project_type",
        lambda _: project_type.DBT,
        raising=True,
    )
    monkeypatch.setattr(
        "tee.importer.dbt.importer.import_dbt_project",
        _fake_import_dbt_project,
        raising=True,
    )

    cmd_import(
        source_project_folder=str(source),
        target_project_folder=str(target),
        format="ots",
        preserve_filenames=True,
        validate_execution=True,
        verbose=True,
    )

    assert called["source_path"] == source.resolve()
    assert called["target_path"] == target.resolve()
    assert called["output_format"] == "ots"
    assert called["preserve_filenames"] is True
    assert called["validate_execution"] is True
    assert called["verbose"] is True
