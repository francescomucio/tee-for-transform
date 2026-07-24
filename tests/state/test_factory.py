"""#20 step 6: backend selection wiring.

`create_state_backend` is the single place `environments.<env>.state.backend`
gets read to decide which `StateBackend` implementation a (project,
environment) pair gets. The critical regression-safety property: omitting
the config entirely (or setting it to "local") must construct exactly the
same `LocalStateBackend` as before this option existed.
"""

import tomllib
from pathlib import Path

import pytest

from t4t.engine.config import get_state_backend_name
from t4t.state.backend import LocalStateBackend
from t4t.state.factory import create_state_backend
from t4t.state.warehouse_backend import WarehouseStateBackend


def _write_project_toml(project_folder: Path, body: str) -> None:
    (project_folder / "project.toml").write_text(body, encoding="utf-8")


class TestGetStateBackendName:
    def test_no_env_name_returns_local(self, tmp_path: Path) -> None:
        assert get_state_backend_name(tmp_path, None) == "local"

    def test_no_project_toml_returns_local(self, tmp_path: Path) -> None:
        assert get_state_backend_name(tmp_path, "dev") == "local"

    def test_env_with_no_state_section_returns_local(self, tmp_path: Path) -> None:
        _write_project_toml(
            tmp_path,
            """
            [environments.dev.connection]
            type = "duckdb"
            path = "data/dev.duckdb"
            """,
        )
        assert get_state_backend_name(tmp_path, "dev") == "local"

    def test_explicit_local_returns_local(self, tmp_path: Path) -> None:
        _write_project_toml(
            tmp_path,
            """
            [environments.dev.state]
            backend = "local"
            """,
        )
        assert get_state_backend_name(tmp_path, "dev") == "local"

    def test_warehouse_returns_warehouse(self, tmp_path: Path) -> None:
        _write_project_toml(
            tmp_path,
            """
            [environments.prod.state]
            backend = "warehouse"
            """,
        )
        assert get_state_backend_name(tmp_path, "prod") == "warehouse"

    def test_unrecognized_value_falls_back_to_local(self, tmp_path: Path) -> None:
        _write_project_toml(
            tmp_path,
            """
            [environments.dev.state]
            backend = "s3"
            """,
        )
        assert get_state_backend_name(tmp_path, "dev") == "local"

    def test_other_environment_unaffected(self, tmp_path: Path) -> None:
        """Config is per-environment: a `warehouse` backend for `prod` must
        not leak into `dev`."""
        _write_project_toml(
            tmp_path,
            """
            [environments.prod.state]
            backend = "warehouse"

            [environments.dev.state]
            backend = "local"
            """,
        )
        assert get_state_backend_name(tmp_path, "prod") == "warehouse"
        assert get_state_backend_name(tmp_path, "dev") == "local"

    def test_toml_round_trips_as_expected_by_tomllib(self, tmp_path: Path) -> None:
        """Sanity check on the fixture bodies themselves: confirms the nested
        table syntax used above actually parses to
        `environments.<env>.state.backend`, not some other shape."""
        _write_project_toml(
            tmp_path,
            """
            [environments.prod.state]
            backend = "warehouse"
            """,
        )
        with open(tmp_path / "project.toml", "rb") as f:
            parsed = tomllib.load(f)
        assert parsed["environments"]["prod"]["state"]["backend"] == "warehouse"


class TestCreateStateBackend:
    def test_no_env_name_returns_local_backend(self, tmp_path: Path) -> None:
        backend = create_state_backend(tmp_path, {"type": "duckdb", "path": ":memory:"})
        assert isinstance(backend, LocalStateBackend)
        assert backend.output_dir == tmp_path / "output"
        assert backend.env_name is None

    def test_omitted_config_produces_identical_local_backend(self, tmp_path: Path) -> None:
        """Regression safety (#20 acceptance criterion 2): the exact
        construction LocalStateBackend used before create_state_backend
        existed."""
        _write_project_toml(
            tmp_path,
            """
            [environments.dev.connection]
            type = "duckdb"
            path = "data/dev.duckdb"
            """,
        )
        backend = create_state_backend(
            tmp_path, {"type": "duckdb", "path": ":memory:"}, env_name="dev"
        )
        direct = LocalStateBackend(tmp_path / "output", env_name="dev")

        assert isinstance(backend, LocalStateBackend)
        assert backend.output_dir == direct.output_dir
        assert backend.env_name == direct.env_name
        assert backend._scoped_dir == direct._scoped_dir  # noqa: SLF001

    def test_explicit_local_produces_local_backend(self, tmp_path: Path) -> None:
        _write_project_toml(
            tmp_path,
            """
            [environments.dev.state]
            backend = "local"
            """,
        )
        backend = create_state_backend(
            tmp_path, {"type": "duckdb", "path": ":memory:"}, env_name="dev"
        )
        assert isinstance(backend, LocalStateBackend)

    def test_warehouse_produces_warehouse_backend(self, tmp_path: Path) -> None:
        _write_project_toml(
            tmp_path,
            """
            [environments.prod.state]
            backend = "warehouse"
            """,
        )
        connection_config = {"type": "duckdb", "path": str(tmp_path / "state.duckdb")}
        backend = create_state_backend(tmp_path, connection_config, env_name="prod")
        assert isinstance(backend, WarehouseStateBackend)
        assert backend.connection_config == connection_config
        assert backend.env_name == "prod"

    def test_end_to_end_local_backend_roundtrip_unchanged(self, tmp_path: Path) -> None:
        """Behavior, not just type: append_run/read_latest through the
        factory-selected local backend behaves exactly like constructing
        LocalStateBackend directly."""
        from t4t.state.manifest import NodeResult, RunManifest

        manifest = RunManifest(
            schema_version=2,
            t4t_version="0.1.0",
            run_id="run-1",
            command="run",
            started_at="2026-01-01T00:00:00+00:00",
            finished_at="2026-01-01T00:01:00+00:00",
            project_root=str(tmp_path),
            config_hash=None,
            vars_hash=None,
            execution_order=["a"],
            nodes=[NodeResult(name="a", status="success", row_count=1)],
            functions=[],
        )
        backend = create_state_backend(tmp_path, {"type": "duckdb", "path": ":memory:"})
        backend.append_run(manifest)

        direct = LocalStateBackend(tmp_path / "output")
        read_back = direct.read_latest()
        assert read_back is not None
        assert read_back.run_id == "run-1"


@pytest.mark.parametrize("backend_value", ["local", None])
def test_local_is_the_default_backend(tmp_path: Path, backend_value) -> None:
    if backend_value is not None:
        _write_project_toml(
            tmp_path,
            f"""
            [environments.dev.state]
            backend = "{backend_value}"
            """,
        )
    assert get_state_backend_name(tmp_path, "dev") == "local"
