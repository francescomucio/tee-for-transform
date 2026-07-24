"""#20 step 7 / acceptance criterion 4: switching `local` -> `warehouse` (or
back) between two runs of the same project produces the documented
no-migration, fail-open-on-missing-baseline behavior -- the first run under
the new backend treats every model as having no baseline (fail-open,
matching #13's fingerprint_spec_version-mismatch philosophy), not a crash
and not a misread of the old backend's state.
"""

from pathlib import Path

from t4t.state.factory import create_state_backend


def _write_project_toml(project_folder: Path, backend: str) -> None:
    (project_folder / "project.toml").write_text(
        f"""
        [environments.prod.state]
        backend = "{backend}"
        """,
        encoding="utf-8",
    )


class TestLocalToWarehouseSwitch:
    def test_run_manifest_not_visible_after_switching_to_warehouse(self, tmp_path: Path) -> None:
        connection_config = {"type": "duckdb", "path": str(tmp_path / "data.duckdb")}

        _write_project_toml(tmp_path, "local")
        local_backend = create_state_backend(tmp_path, connection_config, env_name="prod")
        from t4t.state.manifest import NodeResult, RunManifest

        manifest = RunManifest(
            schema_version=2,
            t4t_version="0.1.0",
            run_id="run-under-local",
            command="run",
            started_at="2026-01-01T00:00:00+00:00",
            finished_at="2026-01-01T00:01:00+00:00",
            project_root=str(tmp_path),
            config_hash=None,
            vars_hash=None,
            execution_order=["analytics.a"],
            nodes=[NodeResult(name="analytics.a", status="success", row_count=1)],
            functions=[],
        )
        local_backend.append_run(manifest)
        assert local_backend.read_latest().run_id == "run-under-local"

        # Switch the environment to the warehouse backend between runs.
        _write_project_toml(tmp_path, "warehouse")
        warehouse_backend = create_state_backend(tmp_path, connection_config, env_name="prod")

        # Fail-open: no crash, no misread of the local run -- simply no
        # baseline yet under the new backend.
        assert warehouse_backend.read_latest() is None

    def test_fingerprint_not_visible_after_switching_to_warehouse(self, tmp_path: Path) -> None:
        connection_config = {"type": "duckdb", "path": str(tmp_path / "data.duckdb")}

        _write_project_toml(tmp_path, "local")
        local_backend = create_state_backend(tmp_path, connection_config, env_name="prod")
        local_backend.save_fingerprint("analytics.orders", "s1", "c1", "f1", 1)
        assert local_backend.read_fingerprint("analytics.orders") is not None

        _write_project_toml(tmp_path, "warehouse")
        warehouse_backend = create_state_backend(tmp_path, connection_config, env_name="prod")
        assert warehouse_backend.read_fingerprint("analytics.orders") is None


class TestWarehouseToLocalSwitch:
    def test_run_manifest_not_visible_after_switching_to_local(self, tmp_path: Path) -> None:
        connection_config = {"type": "duckdb", "path": str(tmp_path / "data.duckdb")}

        _write_project_toml(tmp_path, "warehouse")
        warehouse_backend = create_state_backend(tmp_path, connection_config, env_name="prod")
        from t4t.state.manifest import NodeResult, RunManifest

        manifest = RunManifest(
            schema_version=2,
            t4t_version="0.1.0",
            run_id="run-under-warehouse",
            command="run",
            started_at="2026-01-01T00:00:00+00:00",
            finished_at="2026-01-01T00:01:00+00:00",
            project_root=str(tmp_path),
            config_hash=None,
            vars_hash=None,
            execution_order=["analytics.a"],
            nodes=[NodeResult(name="analytics.a", status="success", row_count=1)],
            functions=[],
        )
        warehouse_backend.append_run(manifest)
        assert warehouse_backend.read_latest().run_id == "run-under-warehouse"

        _write_project_toml(tmp_path, "local")
        local_backend = create_state_backend(tmp_path, connection_config, env_name="prod")
        assert local_backend.read_latest() is None

    def test_switching_does_not_raise(self, tmp_path: Path) -> None:
        """Explicitly: no crash in either direction, for both read paths."""
        connection_config = {"type": "duckdb", "path": str(tmp_path / "data.duckdb")}

        _write_project_toml(tmp_path, "warehouse")
        warehouse_backend = create_state_backend(tmp_path, connection_config, env_name="prod")
        warehouse_backend.save_fingerprint("analytics.orders", "s1", "c1", "f1", 1)

        _write_project_toml(tmp_path, "local")
        local_backend = create_state_backend(tmp_path, connection_config, env_name="prod")
        assert local_backend.read_fingerprint("analytics.orders") is None
        assert local_backend.read_latest() is None
