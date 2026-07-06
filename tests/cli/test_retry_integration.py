"""
Integration tests: persisted manifest + --retry selection on a real temp project.

Uses the CLI (Typer runner) end-to-end: run -> last_run.json -> run --retry.

Note: `t4t run` executes every model in order; downstream models may appear as
failed (missing upstream) rather than skipped like `t4t build`. Retry still selects
the full failed subgraph for re-execution.
"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from t4t.cli.main import app
from t4t.state.manifest import manifest_from_dict


def _write_retry_chain_project(root: Path) -> Path:
    """Minimal project: rtr.retry_a fails; rtr.retry_b and rtr.retry_c depend upstream."""
    (root / "models" / "rtr").mkdir(parents=True)
    (root / "data").mkdir(parents=True)
    (root / "tests").mkdir(parents=True)

    db_path = root / "data" / "retry_e2e.duckdb"
    (root / "project.toml").write_text(
        f'''project_folder = "retry_e2e"
[environments.dev.connection]
type = "duckdb"
path = "{db_path.as_posix()}"
''',
        encoding="utf-8",
    )

    (root / "models" / "rtr" / "retry_a.sql").write_text(
        "SELECT * FROM __nonexistent_table_retry_e2e__\n",
        encoding="utf-8",
    )
    (root / "models" / "rtr" / "retry_b.sql").write_text(
        "SELECT * FROM retry_a\n",
        encoding="utf-8",
    )
    (root / "models" / "rtr" / "retry_c.sql").write_text(
        "SELECT * FROM retry_b\n",
        encoding="utf-8",
    )
    return root.resolve()


@pytest.fixture
def retry_project(tmp_path: Path) -> Path:
    return _write_retry_chain_project(tmp_path / "proj")


class TestRetryIntegration:
    """End-to-end checks for run manifest and --retry."""

    def test_run_writes_manifest_then_retry_filters_to_failed_chain(
        self, retry_project: Path
    ) -> None:
        runner = CliRunner()
        last_run = retry_project / "output" / "dev" / "last_run.json"

        r1 = runner.invoke(
            app,
            ["run", str(retry_project)],
            catch_exceptions=False,
        )
        assert r1.exit_code == 0, r1.stdout + r1.stderr

        assert last_run.is_file(), "last_run.json should exist after t4t run"
        data = json.loads(last_run.read_text(encoding="utf-8"))
        manifest = manifest_from_dict(data)
        by_name = {n.name: n for n in manifest.nodes}

        names = {"rtr.retry_a", "rtr.retry_b", "rtr.retry_c"}
        assert names == {n.name for n in manifest.nodes}
        # Run path executes every model in order; upstream SQL errors surface as failures on
        # downstream models too (not build-style "skipped"). All three still belong in retry.
        assert all(by_name[n].status == "failed" for n in names)

        r2 = runner.invoke(
            app,
            ["run", str(retry_project), "--retry"],
            catch_exceptions=False,
        )
        assert r2.exit_code == 0, r2.stdout + r2.stderr
        out = r2.stdout + r2.stderr
        assert "Filtered to 3 models" in out
        assert "from 3 total" in out
