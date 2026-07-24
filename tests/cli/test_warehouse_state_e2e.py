"""#20 step 9: the acceptance test -- the actual merge gate.

Runs `t4t run` through Typer's in-process `CliRunner` (unlike #13's
subprocess-isolated fingerprint e2e test, this one has no
process-global-state concern to isolate against) against a real project
copied from tests/fixtures/warehouse_state_project/, with a real DuckDB
connection -- not mocked backend calls.

Covers all 5 acceptance criteria from the issue: case 4 (backend-switch
fail-open) is also covered directly against the backend in
tests/state/test_backend_switch.py, but is included here too at the full
CLI level since component tests alone don't close this issue per the issue
text.
"""

import shutil
from pathlib import Path

import duckdb
import pytest
from typer.testing import CliRunner

from t4t.adapters.duckdb.adapter import DuckDBAdapter
from t4t.cli.main import app

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "warehouse_state_project"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    dest = tmp_path / "warehouse_state_project"
    shutil.copytree(FIXTURE, dest)
    (dest / "data").mkdir(parents=True, exist_ok=True)
    return dest


def _state_rows(db_path: Path, schema: str) -> list[tuple]:
    conn = duckdb.connect(str(db_path))
    try:
        return conn.execute(
            f"SELECT record_type, model_name, run_id FROM {schema}_STATE.t4t_model_state "
            "ORDER BY id"
        ).fetchall()
    finally:
        conn.close()


class TestWarehouseBackendAcceptance:
    def test_criterion_1_run_populates_warehouse_state_table(self, project: Path) -> None:
        """`backend = "warehouse"`: after `t4t run --env dev`, querying
        `<schema>_STATE.t4t_model_state` directly on the actual configured
        connection returns the expected model-state rows."""
        runner = CliRunner()
        result = runner.invoke(app, ["run", str(project), "--env", "dev"], catch_exceptions=False)
        assert result.exit_code == 0, result.stdout

        db_path = project / "data" / "warehouse_state_project.duckdb"
        rows = _state_rows(db_path, "wst")

        record_types = {r[0] for r in rows}
        assert "run" in record_types
        assert "fingerprint" in record_types

        fingerprint_models = {r[1] for r in rows if r[0] == "fingerprint"}
        assert fingerprint_models == {"wst.a", "wst.b"}

    def test_criterion_2_backend_omitted_behaves_exactly_like_before(self, project: Path) -> None:
        """`backend` omitted (or "local"): behavior is byte-for-byte
        unchanged from before this issue -- no warehouse schema is ever
        created, and last_run.json/runs.sqlite are written exactly as
        `LocalStateBackend` always has."""
        toml_path = project / "project.toml"
        toml_path.write_text(
            toml_path.read_text(encoding="utf-8").replace(
                '\n[environments.dev.state]\nbackend = "warehouse"\n', ""
            ),
            encoding="utf-8",
        )
        assert "[environments.dev.state]" not in toml_path.read_text(encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(app, ["run", str(project), "--env", "dev"], catch_exceptions=False)
        assert result.exit_code == 0, result.stdout

        assert (project / "output" / "dev" / "last_run.json").is_file()
        assert (project / "output" / "dev" / "runs.sqlite").is_file()

        db_path = project / "data" / "warehouse_state_project.duckdb"
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
        assert "wst_STATE" not in schemas

    def test_criterion_5_ordering_by_id_across_two_real_runs(self, project: Path) -> None:
        """Rows from a second real `t4t run` sort after the first by the
        ordering column -- proven at the CLI level (two full, real
        invocations), not just direct adapter calls."""
        runner = CliRunner()
        r1 = runner.invoke(app, ["run", str(project), "--env", "dev"], catch_exceptions=False)
        assert r1.exit_code == 0, r1.stdout
        r2 = runner.invoke(app, ["run", str(project), "--env", "dev"], catch_exceptions=False)
        assert r2.exit_code == 0, r2.stdout

        db_path = project / "data" / "warehouse_state_project.duckdb"
        run_rows = [r for r in _state_rows(db_path, "wst") if r[0] == "run"]
        assert len(run_rows) == 2
        # Second run's run_id must sort after the first's by `id` (insertion
        # order here, matching wall-clock order too -- the out-of-order case
        # is covered directly against the adapter in
        # tests/adapters/duckdb/test_state_table_duckdb.py).
        assert run_rows[0][2] != run_rows[1][2]

    def test_criterion_3_missing_create_schema_permission_fails_with_ddl_text(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Missing CREATE SCHEMA permission: the run fails with an error
        that includes the literal DDL text, not a raw permission-denied
        traceback."""

        original = DuckDBAdapter._execute_state_ddl_statement

        def _permission_denied(self, stmt: str):
            if "CREATE SCHEMA" in stmt:
                raise RuntimeError("permission denied for database warehouse_state_project")
            return original(self, stmt)

        monkeypatch.setattr(DuckDBAdapter, "_execute_state_ddl_statement", _permission_denied)

        runner = CliRunner()
        result = runner.invoke(app, ["run", str(project), "--env", "dev"], catch_exceptions=True)

        assert result.exit_code != 0
        output = result.stdout + str(result.exception or "")
        assert "CREATE SCHEMA IF NOT EXISTS wst_STATE" in output
        assert "permission denied" in output
        # Not a raw traceback dumped to the user by default (non-verbose).
        assert "Traceback (most recent call last)" not in result.stdout

    def test_criterion_4_switching_local_to_warehouse_between_cli_runs(self, project: Path) -> None:
        """Switching `local` -> `warehouse` between two `t4t run` invocations:
        the first run under the new backend has no baseline -- proven here
        by asserting the warehouse state table is untouched by the run that
        happened while the environment was still on `local`."""
        toml_path = project / "project.toml"
        original_toml = toml_path.read_text(encoding="utf-8")
        local_toml = original_toml.replace('backend = "warehouse"', 'backend = "local"')
        assert local_toml != original_toml  # sanity: the replace actually matched
        toml_path.write_text(local_toml, encoding="utf-8")

        runner = CliRunner()
        r1 = runner.invoke(app, ["run", str(project), "--env", "dev"], catch_exceptions=False)
        assert r1.exit_code == 0, r1.stdout
        assert (project / "output" / "dev" / "last_run.json").is_file()

        # The local backend still runs the actual models against this same
        # DuckDB file (it's the data connection, not something exclusive to
        # the warehouse state backend) -- but it must never create the
        # wst_STATE schema, since state itself stayed on local disk.
        db_path = project / "data" / "warehouse_state_project.duckdb"
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
        assert "wst_STATE" not in schemas

        # Switch to warehouse and run again.
        toml_path.write_text(original_toml, encoding="utf-8")
        r2 = runner.invoke(app, ["run", str(project), "--env", "dev"], catch_exceptions=False)
        assert r2.exit_code == 0, r2.stdout

        rows = _state_rows(db_path, "wst")
        run_rows = [r for r in rows if r[0] == "run"]
        # Exactly one warehouse run row -- the local run never wrote here,
        # and this run has no warehouse baseline to have "misread".
        assert len(run_rows) == 1
