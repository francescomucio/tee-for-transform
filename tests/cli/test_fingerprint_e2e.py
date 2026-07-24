"""Step 9: the #13 acceptance test -- the actual merge gate.

Runs `t4t` as a *real subprocess* (`python -m t4t.cli.main ...`), not
Typer's in-process CliRunner, against a real multi-model project copied from
tests/fixtures/fingerprint_project/ -- not mocked dependency data.

Subprocess isolation is required specifically for case 7 (shared Python
imports): a Python model's `import shared_helper` populates the real,
process-global `sys.modules` cache. If two `t4t run` invocations shared one
Python process (as they would with in-process CliRunner), the second
invocation's `SharedImportTracker` baseline would already include
`shared_helper` from the first invocation, masking the exact behavior this
test needs to prove. A fresh subprocess per invocation matches how `t4t run`
is actually used in practice (a fresh process every time), so this isn't a
test-only workaround for a production bug -- see
tests/cli/test_logging_e2e.py for the same rationale applied to #36.

Covers all 7 acceptance criteria from the issue in one project:

1. Reformatting a model's SQL (whitespace *and* comments) -> fingerprint unchanged.
2. Changing a model's query logic -> sql_hash changed, fingerprint changed.
3. Changing only a model's config -> config_hash changed, sql_hash unchanged,
   fingerprint changed.
4. Changing an unrelated model -> this model's sql_hash/config_hash/fingerprint
   all unchanged.
5. Changing a direct upstream dependency's SQL -> this model's own
   sql_hash/config_hash unchanged, fingerprint changed.
6. Changing a transitive (grandparent) dependency -> fingerprint changed,
   own sql_hash/config_hash unchanged.
7. A Python model importing a shared project-local helper file: editing the
   helper changes the importing model's fingerprint (own sql_hash
   unchanged); a second, unrelated Python model importing the same
   already-cached helper shows the same result.
"""

import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "fingerprint_project"


@dataclass
class FP:
    model_name: str
    sql_hash: str
    config_hash: str
    fingerprint: str


def _run_t4t(project: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "t4t.cli.main", "run", str(project)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=120,
    )


def _read_fingerprints(project: Path) -> dict[str, FP]:
    db_path = project / "output" / "dev" / "runs.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT model_name, sql_hash, config_hash, fingerprint FROM fingerprints"
        ).fetchall()
    finally:
        conn.close()
    return {r[0]: FP(r[0], r[1], r[2], r[3]) for r in rows}


@pytest.fixture
def project(tmp_path: Path) -> Path:
    dest = tmp_path / "fingerprint_project"
    shutil.copytree(FIXTURE, dest)
    (dest / "data").mkdir(parents=True, exist_ok=True)
    return dest


class TestFingerprintAcceptance:
    def test_seven_case_acceptance(self, project: Path) -> None:
        # --- Baseline run ---
        r0 = _run_t4t(project)
        assert r0.returncode == 0, r0.stdout + r0.stderr
        before = _read_fingerprints(project)

        expected = {
            "fp.a",
            "fp.b",
            "fp.c",
            "fp.unrelated",
            "fp.reformat_target",
            "fp.logic_target",
            "fp.config_target",
            "fp.py_model_1",
            "fp.py_model_2",
        }
        assert expected.issubset(before.keys())

        # --- Apply edits for cases 1, 2, 3, 5, 6 (all independent models/files,
        # applied together and verified in one second run) ---

        # Case 1: reformat only (whitespace + comment change, no logic change).
        (project / "models" / "fp" / "reformat_target.sql").write_text(
            "-- a completely different comment\n"
            "SELECT\n"
            "    1    AS   id  -- trailing comment too\n",
            encoding="utf-8",
        )

        # Case 2: real logic change.
        (project / "models" / "fp" / "logic_target.sql").write_text(
            "SELECT 1 AS id, 2 AS extra_column\n", encoding="utf-8"
        )

        # Case 3: config-only change (materialization, inside the SQL comment
        # metadata block -- comments are stripped for sql_hash, so this must
        # not move sql_hash).
        (project / "models" / "fp" / "config_target.sql").write_text(
            '-- metadata: {"schema": [], "materialization": "view"}\nSELECT 1 AS id\n',
            encoding="utf-8",
        )

        # Cases 5 & 6: change fp.a (direct upstream of fp.b, transitive
        # upstream of fp.c via fp.b).
        (project / "models" / "fp" / "a.sql").write_text("SELECT 2 AS id\n", encoding="utf-8")

        # fp.unrelated (case 4) and the Python models (case 7) are
        # deliberately left untouched in this pass.

        r1 = _run_t4t(project)
        assert r1.returncode == 0, r1.stdout + r1.stderr
        after = _read_fingerprints(project)

        # --- Case 1: reformat only -> unchanged sql_hash and fingerprint ---
        assert after["fp.reformat_target"].sql_hash == before["fp.reformat_target"].sql_hash
        assert after["fp.reformat_target"].fingerprint == before["fp.reformat_target"].fingerprint

        # --- Case 2: logic change -> sql_hash changed, fingerprint changed ---
        assert after["fp.logic_target"].sql_hash != before["fp.logic_target"].sql_hash
        assert after["fp.logic_target"].fingerprint != before["fp.logic_target"].fingerprint

        # --- Case 3: config-only change ---
        assert after["fp.config_target"].config_hash != before["fp.config_target"].config_hash
        assert after["fp.config_target"].sql_hash == before["fp.config_target"].sql_hash
        assert after["fp.config_target"].fingerprint != before["fp.config_target"].fingerprint

        # --- Case 4: unrelated model, untouched -> everything unchanged ---
        assert after["fp.unrelated"].sql_hash == before["fp.unrelated"].sql_hash
        assert after["fp.unrelated"].config_hash == before["fp.unrelated"].config_hash
        assert after["fp.unrelated"].fingerprint == before["fp.unrelated"].fingerprint

        # --- Case 5: direct upstream (fp.a) changed -> fp.b's own hashes
        # unchanged, fingerprint changed via the chain ---
        assert after["fp.b"].sql_hash == before["fp.b"].sql_hash
        assert after["fp.b"].config_hash == before["fp.b"].config_hash
        assert after["fp.b"].fingerprint != before["fp.b"].fingerprint

        # --- Case 6: transitive (grandparent) dependency changed -> fp.c's
        # own hashes unchanged, fingerprint changed ---
        assert after["fp.c"].sql_hash == before["fp.c"].sql_hash
        assert after["fp.c"].config_hash == before["fp.c"].config_hash
        assert after["fp.c"].fingerprint != before["fp.c"].fingerprint

        # Sanity: fp.a itself did change.
        assert after["fp.a"].sql_hash != before["fp.a"].sql_hash
        assert after["fp.a"].fingerprint != before["fp.a"].fingerprint

        # --- Case 7: shared Python-import helper edit (separate run, for a
        # clean process/sys.modules baseline) ---
        mid = after  # fp.py_model_1 / fp.py_model_2 unaffected by the pass above
        assert mid["fp.py_model_1"].fingerprint == before["fp.py_model_1"].fingerprint
        assert mid["fp.py_model_2"].fingerprint == before["fp.py_model_2"].fingerprint

        (project / "models" / "fp" / "shared_helper.py").write_text(
            "GREETING = 'goodbye'\n", encoding="utf-8"
        )

        r2 = _run_t4t(project)
        assert r2.returncode == 0, r2.stdout + r2.stderr
        final = _read_fingerprints(project)

        # Both models' own source is untouched -> sql_hash unchanged...
        assert final["fp.py_model_1"].sql_hash == mid["fp.py_model_1"].sql_hash
        assert final["fp.py_model_2"].sql_hash == mid["fp.py_model_2"].sql_hash
        # ...but the shared helper's content is folded into both fingerprints,
        # via the fixed sys.modules baseline (not a per-model incremental
        # one) -- both models change, including py_model_2, which imports
        # shared_helper *after* py_model_1 already cached it.
        assert final["fp.py_model_1"].fingerprint != mid["fp.py_model_1"].fingerprint
        assert final["fp.py_model_2"].fingerprint != mid["fp.py_model_2"].fingerprint
