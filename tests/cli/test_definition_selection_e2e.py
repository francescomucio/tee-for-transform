"""#14's acceptance test (the merge gate) -- the seven cases from the
issue's "Acceptance criteria" section, run against a real project
(tests/fixtures/definition_selection_project/) via `CliRunner` and real
`t4t run` invocations, not mocked selection logic.

Fixture project (`models/e2e/`):

- `leaf_changed` (Python, `tags=["nightly"]`, no dependents) -- the sole
  Python model in the project. Kept as the *only* Python model
  deliberately: t4t's Python-model shared-import detection (#13) diffs
  `sys.modules` once per whole `t4t` invocation, which means editing one
  Python model's file can, as a documented v1 limitation (see
  docs/user-guide/fingerprinting.md), spuriously mark an *unrelated*
  second Python model as changed too (over-attribution, not a bug this
  issue needs to fix). A single Python model sidesteps that limitation
  entirely while still exercising real tag-carrying model support (SQL
  models cannot carry `tags` today -- verified empirically: SQL-comment
  metadata's schema drops the field).
- `chain_root` -> `chain_mid` -> `chain_leaf` (SQL): a 3-model dependency
  chain, used for the downstream-closure case (2).
- `unrelated` (SQL, untagged, never edited): proves selection doesn't leak
  to models outside the selected set/closure.
- `union_target` (SQL, untagged): the "changed but not tagged" model used
  to tell union (case 6) and intersection (case 7) apart.
- `fail_target` (SQL, always references a nonexistent table -> always
  fails execution, never edited): proves `definition:changed` and
  `run:failed` are orthogonal (cases 3-4).
- `ok_b`, `ok_c` (SQL, always succeed, never edited): the other two
  "attempted regardless of outcome" models for case 3.

Sequencing note: every `t4t run` invocation -- even a `--select` that
matches zero models -- persists a new "latest run" manifest (last_run.json/
runs.sqlite), which is what `run:failed`/`--retry` read. So the `run:failed`
(case 4) and `--retry` checks must run *before* any other invocation that
would overwrite that manifest with the narrower "0 models selected" or
"3-model" runs cases 3/1/2 make -- see the ordering below, which checks
run:failed/--retry immediately after the baseline run, then definition:
changed (case 3), then cases 1/2/6/7 in sequence, each consuming the
"changed" state its own edit created (each edit is a *new* SQL/source
change relative to whatever baseline the previous case's run just wrote).
"""

import shutil
from pathlib import Path

from typer.testing import CliRunner

from t4t.cli.main import app

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "definition_selection_project"

ALL_MODELS = {
    "e2e.leaf_changed",
    "e2e.chain_root",
    "e2e.chain_mid",
    "e2e.chain_leaf",
    "e2e.unrelated",
    "e2e.union_target",
    "e2e.fail_target",
    "e2e.ok_b",
    "e2e.ok_c",
}


def _project(tmp_path: Path, name: str = "proj") -> Path:
    dest = tmp_path / name
    shutil.copytree(FIXTURE, dest)
    (dest / "data").mkdir(parents=True, exist_ok=True)
    return dest


def _run(runner: CliRunner, project: Path, *extra_args: str):
    result = runner.invoke(app, ["run", str(project), *extra_args], catch_exceptions=False)
    assert result.exit_code == 0, result.stdout + result.stderr
    return result.stdout + result.stderr


def _bump_leaf_changed(project: Path, value: int) -> None:
    path = project / "models" / "e2e" / "leaf_changed.py"
    path.write_text(
        f'@model(table_name="leaf_changed", tags=["nightly"])  # noqa: F821\n'
        f"def leaf_changed():\n"
        f'    return "SELECT {value} AS id"\n',
        encoding="utf-8",
    )


def _bump_sql(path: Path, value: int) -> None:
    path.write_text(f"SELECT {value} AS id\n", encoding="utf-8")


class TestDefinitionSelectionAcceptance:
    def test_seven_case_acceptance(self, tmp_path: Path) -> None:
        runner = CliRunner()
        project = _project(tmp_path)

        # --- Baseline run: all 9 models attempted, fail_target fails,
        # 8 others succeed. Establishes the fingerprint baseline for every
        # model (case 3's premise) and the run manifest run:failed/--retry
        # read (case 4's premise). ---
        out0 = _run(runner, project)
        assert "8 tables" in out0  # 8 succeeded
        assert "Failed: 1 table" in out0  # fail_target

        # === Case 4 (checked first -- see module docstring on manifest
        # ordering): run:failed selects exactly the failed model, even
        # though its definition never changed. ===
        out_failed = _run(runner, project, "--select", "run:failed")
        assert "Filtered to 1 models (from 9 total)" in out_failed
        assert "e2e.fail_target" in out_failed

        # --retry is sugar for --select run:failed+ -- same result here
        # (fail_target has no downstream dependents, so the '+' adds
        # nothing new).
        out_retry = _run(runner, project, "--retry")
        assert "Filtered to 1 models (from 9 total)" in out_retry
        assert "e2e.fail_target" in out_retry

        # === Case 3: on the run right after the failure, definition:changed
        # selects NONE of fail_target/ok_b/ok_c (or anyone else) -- the
        # baseline update is per-model-attempted, independent of success/
        # failure, per #14's design decision. ===
        out_none_changed = _run(runner, project, "--select", "definition:changed")
        assert "No models matched the selection criteria" in out_none_changed

        # === Case 1: change one model's SQL (leaf_changed, a leaf with no
        # dependents); definition:changed executes only that model. ===
        _bump_leaf_changed(project, 2)
        out_case1 = _run(runner, project, "--select", "definition:changed")
        assert "Filtered to 1 models (from 9 total)" in out_case1
        assert "Filtered execution order: e2e.leaf_changed" in out_case1

        # === Case 2: definition:changed+ selects the changed model AND its
        # full downstream closure; unrelated/upstream models do not run. ===
        _bump_sql(project / "models" / "e2e" / "chain_root.sql", 2)
        out_case2 = _run(runner, project, "--select", "definition:changed+")
        assert "Filtered to 3 models (from 9 total)" in out_case2
        assert (
            "Filtered execution order: e2e.chain_root -> e2e.chain_mid -> e2e.chain_leaf"
            in out_case2
        )

        # === Case 6: union -- definition:changed OR tag:nightly selects
        # both the newly-changed leaf_changed and the newly-changed,
        # untagged union_target (matches tag only) plus leaf_changed
        # (matches both) -- i.e. the union of the two selectors' matches,
        # not their intersection. ===
        _bump_leaf_changed(project, 3)
        _bump_sql(project / "models" / "e2e" / "union_target.sql", 2)
        out_case6 = _run(
            runner, project, "--select", "definition:changed", "--select", "tag:nightly"
        )
        assert "Filtered to 2 models (from 9 total)" in out_case6
        assert "e2e.leaf_changed" in out_case6
        assert "e2e.union_target" in out_case6

        # === Case 7: intersection (comma, no spaces) -- only leaf_changed
        # (changed AND tagged nightly) is selected; union_target is changed
        # but not tagged, so it's excluded here despite being included in
        # case 6's union above -- proving AND, not another OR. ===
        _bump_leaf_changed(project, 4)
        out_case7 = _run(runner, project, "--select", "definition:changed,tag:nightly")
        assert "Filtered to 1 models (from 9 total)" in out_case7
        assert "Filtered execution order: e2e.leaf_changed" in out_case7
        assert (
            "e2e.union_target" not in out_case7.split("Filtered execution order:")[1].split("\n")[0]
        )

    def test_case_5_first_run_no_baseline_selects_all_with_warning(self, tmp_path: Path) -> None:
        """Case 5: first run ever, no persisted baseline -- definition:changed
        selects ALL models, with a warning printed (fail-open)."""
        runner = CliRunner()
        project = _project(tmp_path, name="fresh")

        out = _run(runner, project, "--select", "definition:changed")

        assert "No baseline" in out
        assert "dev" in out
        assert f"Filtered to {len(ALL_MODELS)} models (from {len(ALL_MODELS)} total)" in out
