"""LocalStateBackend persistence."""

import json
from pathlib import Path

from tee.state.backend import LocalStateBackend
from tee.state.manifest import NodeResult, RunManifest


def _minimal_manifest() -> RunManifest:
    return RunManifest(
        schema_version=1,
        t4t_version="0.1.0",
        run_id="00000000-0000-4000-8000-000000000001",
        command="run",
        started_at="2026-01-01T00:00:00+00:00",
        finished_at="2026-01-01T00:01:00+00:00",
        project_root="/tmp",
        config_hash=None,
        vars_hash=None,
        execution_order=["a"],
        nodes=[NodeResult(name="a", status="success", row_count=1)],
        functions=[],
    )


def test_local_backend_append_and_read_json(tmp_path: Path):
    out = tmp_path / "output"
    b = LocalStateBackend(out)
    m = _minimal_manifest()
    b.append_run(m)

    j = out / "last_run.json"
    assert j.is_file()
    data = json.loads(j.read_text())
    assert data["run_id"] == m.run_id

    m2 = b.read_latest()
    assert m2 is not None
    assert m2.run_id == m.run_id
    assert m2.nodes[0].name == "a"


def test_read_latest_fallback_sqlite_without_json(tmp_path: Path):
    out = tmp_path / "output"
    b = LocalStateBackend(out)
    m = _minimal_manifest()
    b.append_run(m)

    (out / "last_run.json").unlink()
    m2 = b.read_latest()
    assert m2 is not None
    assert m2.run_id == m.run_id


def test_manifest_json_invalid_falls_back_to_sqlite(tmp_path: Path):
    out = tmp_path / "output"
    b = LocalStateBackend(out)
    m = _minimal_manifest()
    b.append_run(m)
    (out / "last_run.json").write_text("not json {{{", encoding="utf-8")
    m2 = b.read_latest()
    assert m2 is not None
    assert m2.run_id == m.run_id


def test_read_latest_empty_db(tmp_path: Path):
    b = LocalStateBackend(tmp_path)
    assert b.read_latest() is None
