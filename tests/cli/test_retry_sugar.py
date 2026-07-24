"""#14 step 8: --retry is sugar for --select run:failed+ -- one
implementation, flag is an alias.

Verifies both spellings produce identical selection on the same failure
scenario (two independent copies of the same project, since a run mutates
persisted state). This complements tests/cli/test_retry_integration.py
(which only exercises --retry) by proving --select run:failed+ is not just
parseable but behaviorally identical, end to end, on a real project.
"""

from pathlib import Path

from typer.testing import CliRunner

from t4t.cli.main import app

from .test_retry_integration import _write_retry_chain_project


class TestRetrySugarEquivalence:
    def test_retry_flag_and_explicit_select_produce_same_filtered_count(
        self, tmp_path: Path
    ) -> None:
        runner = CliRunner()

        # Two independent copies of the same failure scenario -- a run
        # mutates persisted state, so --retry and --select run:failed+
        # can't share one project directory.
        project_a = _write_retry_chain_project(tmp_path / "proj_a")
        project_b = _write_retry_chain_project(tmp_path / "proj_b")

        # Baseline (failing) run on both.
        r_a0 = runner.invoke(app, ["run", str(project_a)], catch_exceptions=False)
        assert r_a0.exit_code == 0, r_a0.stdout + r_a0.stderr
        r_b0 = runner.invoke(app, ["run", str(project_b)], catch_exceptions=False)
        assert r_b0.exit_code == 0, r_b0.stdout + r_b0.stderr

        # A: --retry: B: --select run:failed+
        r_a1 = runner.invoke(app, ["run", str(project_a), "--retry"], catch_exceptions=False)
        r_b1 = runner.invoke(
            app, ["run", str(project_b), "--select", "run:failed+"], catch_exceptions=False
        )

        assert r_a1.exit_code == 0, r_a1.stdout + r_a1.stderr
        assert r_b1.exit_code == 0, r_b1.stdout + r_b1.stderr

        out_a = r_a1.stdout + r_a1.stderr
        out_b = r_b1.stdout + r_b1.stderr
        assert "Filtered to 3 models" in out_a
        assert "Filtered to 3 models" in out_b
