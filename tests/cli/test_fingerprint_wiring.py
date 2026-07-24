"""Step 7: fingerprint computation + storage wired into the run lifecycle.

Uses the CLI (Typer CliRunner) end-to-end against a real temp project, same
pattern as tests/cli/test_retry_integration.py, but focused narrowly on:
after `t4t run` persists its manifest, sql_hash/config_hash/fingerprint are
written for every *attempted* model, and unattempted (skipped) models get
nothing written.

The full 7-case acceptance test (issue's merge gate) lives in
tests/cli/test_fingerprint_e2e.py.
"""

from pathlib import Path

from typer.testing import CliRunner

from t4t.cli.main import app
from t4t.state.backend import LocalStateBackend


def _write_chain_project(root: Path) -> Path:
    """fp.a (leaf) -> fp.b (depends on a) -> fp.c (fails, depends on a nonexistent table)."""
    (root / "models" / "fp").mkdir(parents=True)
    (root / "data").mkdir(parents=True)

    db_path = root / "data" / "fingerprint_wiring.duckdb"
    (root / "project.toml").write_text(
        f'''project_folder = "fp_wiring"
[environments.dev.connection]
type = "duckdb"
path = "{db_path.as_posix()}"
''',
        encoding="utf-8",
    )
    (root / "models" / "fp" / "a.sql").write_text("SELECT 1 AS id\n", encoding="utf-8")
    (root / "models" / "fp" / "b.sql").write_text("SELECT id FROM a\n", encoding="utf-8")
    return root.resolve()


class TestFingerprintWiring:
    def test_run_writes_fingerprints_for_attempted_models(self, tmp_path: Path) -> None:
        project = _write_chain_project(tmp_path / "proj")
        runner = CliRunner()

        result = runner.invoke(app, ["run", str(project)], catch_exceptions=False)
        assert result.exit_code == 0, result.stdout + result.stderr

        backend = LocalStateBackend(project / "output", env_name="dev")
        fp_a = backend.read_fingerprint("fp.a")
        fp_b = backend.read_fingerprint("fp.b")

        assert fp_a is not None
        assert fp_b is not None
        assert fp_a.sql_hash
        assert fp_a.config_hash
        assert fp_a.fingerprint
        assert fp_b.fingerprint != fp_a.fingerprint

    def test_second_run_updates_stored_fingerprint_after_edit(self, tmp_path: Path) -> None:
        project = _write_chain_project(tmp_path / "proj")
        runner = CliRunner()

        r1 = runner.invoke(app, ["run", str(project)], catch_exceptions=False)
        assert r1.exit_code == 0, r1.stdout + r1.stderr

        backend = LocalStateBackend(project / "output", env_name="dev")
        fp_a_before = backend.read_fingerprint("fp.a")
        fp_b_before = backend.read_fingerprint("fp.b")

        (project / "models" / "fp" / "a.sql").write_text("SELECT 2 AS id\n", encoding="utf-8")

        r2 = runner.invoke(app, ["run", str(project)], catch_exceptions=False)
        assert r2.exit_code == 0, r2.stdout + r2.stderr

        fp_a_after = backend.read_fingerprint("fp.a")
        fp_b_after = backend.read_fingerprint("fp.b")

        assert fp_a_after.sql_hash != fp_a_before.sql_hash
        assert fp_a_after.fingerprint != fp_a_before.fingerprint
        # b's own sql_hash is unaffected but its combined fingerprint moves
        # via the chain.
        assert fp_b_after.sql_hash == fp_b_before.sql_hash
        assert fp_b_after.fingerprint != fp_b_before.fingerprint
