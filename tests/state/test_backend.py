"""LocalStateBackend persistence."""

import json
from pathlib import Path

from t4t.state.backend import LocalStateBackend
from t4t.state.manifest import NodeResult, RunManifest


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


class TestFingerprintStorage:
    """Storage-only tests for #13 step 2: store/retrieve sql_hash, config_hash,
    and fingerprint as three separate fields per model per environment. No
    hashing logic involved -- values here are arbitrary opaque strings."""

    def test_save_and_read_fingerprint_roundtrip(self, tmp_path: Path) -> None:
        b = LocalStateBackend(tmp_path / "output", env_name="dev")
        b.save_fingerprint(
            model_name="schema.model_a",
            sql_hash="sql-hash-1",
            config_hash="config-hash-1",
            fingerprint="fingerprint-1",
            fingerprint_spec_version=1,
        )

        record = b.read_fingerprint("schema.model_a")
        assert record is not None
        assert record.model_name == "schema.model_a"
        assert record.sql_hash == "sql-hash-1"
        assert record.config_hash == "config-hash-1"
        assert record.fingerprint == "fingerprint-1"
        assert record.fingerprint_spec_version == 1
        assert record.updated_at is not None

    def test_read_fingerprint_missing_model_returns_none(self, tmp_path: Path) -> None:
        b = LocalStateBackend(tmp_path / "output", env_name="dev")
        assert b.read_fingerprint("schema.does_not_exist") is None

    def test_read_fingerprint_no_db_yet_returns_none(self, tmp_path: Path) -> None:
        b = LocalStateBackend(tmp_path / "output", env_name="dev")
        assert b.read_fingerprint("schema.model_a") is None

    def test_save_fingerprint_overwrites_existing(self, tmp_path: Path) -> None:
        b = LocalStateBackend(tmp_path / "output", env_name="dev")
        b.save_fingerprint("schema.model_a", "s1", "c1", "f1", 1)
        b.save_fingerprint("schema.model_a", "s2", "c2", "f2", 1)

        record = b.read_fingerprint("schema.model_a")
        assert record is not None
        assert record.sql_hash == "s2"
        assert record.config_hash == "c2"
        assert record.fingerprint == "f2"

    def test_fingerprints_scoped_per_environment(self, tmp_path: Path) -> None:
        dev = LocalStateBackend(tmp_path / "output", env_name="dev")
        prod = LocalStateBackend(tmp_path / "output", env_name="prod")

        dev.save_fingerprint("schema.model_a", "dev-sql", "dev-cfg", "dev-fp", 1)
        prod.save_fingerprint("schema.model_a", "prod-sql", "prod-cfg", "prod-fp", 1)

        assert dev.read_fingerprint("schema.model_a").sql_hash == "dev-sql"
        assert prod.read_fingerprint("schema.model_a").sql_hash == "prod-sql"

    def test_multiple_models_independent(self, tmp_path: Path) -> None:
        b = LocalStateBackend(tmp_path / "output", env_name="dev")
        b.save_fingerprint("schema.model_a", "sa", "ca", "fa", 1)
        b.save_fingerprint("schema.model_b", "sb", "cb", "fb", 1)

        a = b.read_fingerprint("schema.model_a")
        b2 = b.read_fingerprint("schema.model_b")
        assert a.sql_hash == "sa"
        assert b2.sql_hash == "sb"
