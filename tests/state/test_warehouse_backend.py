"""#20 step 5: WarehouseStateBackend round-tripping the full StateBackend
Protocol against a real DuckDB connection (file-based, not `:memory:` --
each call opens its own short-lived connection, so an in-memory database
would not persist data across calls, unlike a real warehouse)."""

from pathlib import Path

import pytest

from t4t.state.backend import StateBackend
from t4t.state.fingerprint import StoredFingerprint
from t4t.state.manifest import NodeResult, RunManifest
from t4t.state.warehouse_backend import WarehouseStateBackend


def _connection_config(db_path: Path, schema: str = "analytics") -> dict:
    return {"type": "duckdb", "path": str(db_path), "schema": schema}


def _manifest(run_id: str) -> RunManifest:
    return RunManifest(
        schema_version=2,
        t4t_version="0.1.0",
        run_id=run_id,
        command="run",
        started_at="2026-01-01T00:00:00+00:00",
        finished_at="2026-01-01T00:01:00+00:00",
        project_root="/tmp/project",
        config_hash=None,
        vars_hash=None,
        execution_order=["analytics.a"],
        nodes=[NodeResult(name="analytics.a", status="success", row_count=1)],
        functions=[],
    )


class TestWarehouseStateBackendProtocolConformance:
    def test_satisfies_state_backend_protocol(self, tmp_path: Path) -> None:
        backend = WarehouseStateBackend(_connection_config(tmp_path / "state.duckdb"))
        assert isinstance(backend, StateBackend)


class TestWarehouseStateBackendRunManifest:
    def test_append_and_read_latest_roundtrip(self, tmp_path: Path) -> None:
        backend = WarehouseStateBackend(_connection_config(tmp_path / "state.duckdb"))
        manifest = _manifest("run-1")
        backend.append_run(manifest)

        latest = backend.read_latest()
        assert latest is not None
        assert latest.run_id == "run-1"
        assert latest.nodes[0].name == "analytics.a"

    def test_read_latest_returns_most_recently_appended(self, tmp_path: Path) -> None:
        backend = WarehouseStateBackend(_connection_config(tmp_path / "state.duckdb"))
        backend.append_run(_manifest("run-1"))
        backend.append_run(_manifest("run-2"))

        latest = backend.read_latest()
        assert latest.run_id == "run-2"

    def test_read_latest_no_runs_returns_none(self, tmp_path: Path) -> None:
        backend = WarehouseStateBackend(_connection_config(tmp_path / "state.duckdb"))
        assert backend.read_latest() is None

    def test_run_manifest_lands_in_expected_schema_table(self, tmp_path: Path) -> None:
        """Acceptance criterion 1: querying `<schema>_STATE.t4t_model_state`
        directly on the actual configured connection returns the expected
        rows."""
        import duckdb

        db_path = tmp_path / "state.duckdb"
        backend = WarehouseStateBackend(_connection_config(db_path, schema="analytics"))
        backend.append_run(_manifest("run-1"))

        conn = duckdb.connect(str(db_path))
        try:
            rows = conn.execute(
                "SELECT record_type, run_id FROM analytics_STATE.t4t_model_state "
                "WHERE record_type = 'run'"
            ).fetchall()
        finally:
            conn.close()
        assert rows == [("run", "run-1")]


class TestWarehouseStateBackendFingerprint:
    def test_save_and_read_fingerprint_roundtrip(self, tmp_path: Path) -> None:
        backend = WarehouseStateBackend(_connection_config(tmp_path / "state.duckdb"))
        backend.save_fingerprint(
            model_name="analytics.orders",
            sql_hash="sql-1",
            config_hash="cfg-1",
            fingerprint="fp-1",
            fingerprint_spec_version=1,
        )

        record = backend.read_fingerprint("analytics.orders")
        assert record is not None
        assert isinstance(record, StoredFingerprint)
        assert record.model_name == "analytics.orders"
        assert record.sql_hash == "sql-1"
        assert record.config_hash == "cfg-1"
        assert record.fingerprint == "fp-1"
        assert record.fingerprint_spec_version == 1
        assert record.updated_at is not None

    def test_read_fingerprint_missing_model_returns_none(self, tmp_path: Path) -> None:
        backend = WarehouseStateBackend(_connection_config(tmp_path / "state.duckdb"))
        assert backend.read_fingerprint("analytics.missing") is None

    def test_fingerprint_routed_to_models_own_schema_not_default(self, tmp_path: Path) -> None:
        """A model in a different schema than the environment's configured
        default schema still gets its own `<schema>_STATE` table -- state
        is per data schema, not per connection default."""
        import duckdb

        db_path = tmp_path / "state.duckdb"
        # Default/connection schema is "analytics", but the model itself is
        # in "staging".
        backend = WarehouseStateBackend(_connection_config(db_path, schema="analytics"))
        backend.save_fingerprint("staging.raw_orders", "s1", "c1", "f1", 1)

        conn = duckdb.connect(str(db_path))
        try:
            schemas = {
                r[0]
                for r in conn.execute(
                    "SELECT schema_name FROM information_schema.schemata"
                ).fetchall()
            }
        finally:
            conn.close()
        assert "staging_STATE" in schemas
        assert "analytics_STATE" not in schemas  # never touched -- no run appended

    def test_multiple_models_independent(self, tmp_path: Path) -> None:
        backend = WarehouseStateBackend(_connection_config(tmp_path / "state.duckdb"))
        backend.save_fingerprint("analytics.a", "sa", "ca", "fa", 1)
        backend.save_fingerprint("analytics.b", "sb", "cb", "fb", 1)

        a = backend.read_fingerprint("analytics.a")
        b = backend.read_fingerprint("analytics.b")
        assert a.sql_hash == "sa"
        assert b.sql_hash == "sb"


class TestEnsureSchemasForModels:
    def test_ensure_schemas_creates_state_tables_for_all_touched_schemas(
        self, tmp_path: Path
    ) -> None:
        import duckdb

        db_path = tmp_path / "state.duckdb"
        backend = WarehouseStateBackend(_connection_config(db_path, schema="analytics"))
        backend.ensure_schemas_for_models({"analytics.a", "staging.raw"})

        conn = duckdb.connect(str(db_path))
        try:
            schemas = {
                r[0]
                for r in conn.execute(
                    "SELECT schema_name FROM information_schema.schemata"
                ).fetchall()
            }
        finally:
            conn.close()
        # Default (connection) schema + both models' schemas.
        assert {"analytics_STATE", "staging_STATE"} <= schemas

    def test_ensure_schemas_fails_whole_call_on_any_ddl_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from t4t.adapters.duckdb.adapter import DuckDBAdapter

        original = DuckDBAdapter.ensure_state_table
        call_log: list[str] = []

        def _flaky_ensure(self, data_schema: str) -> None:
            call_log.append(data_schema)
            if data_schema == "staging_STATE" or data_schema == "staging":
                raise RuntimeError("permission denied")
            return original(self, data_schema)

        monkeypatch.setattr(DuckDBAdapter, "ensure_state_table", _flaky_ensure)

        db_path = tmp_path / "state.duckdb"
        backend = WarehouseStateBackend(_connection_config(db_path, schema="analytics"))
        with pytest.raises(RuntimeError, match="permission denied"):
            backend.ensure_schemas_for_models({"analytics.a", "staging.raw"})
