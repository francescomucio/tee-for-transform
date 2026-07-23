"""
Subprocess-level acceptance tests for GitHub issue #36 (structured logging).

These run `t4t` as a *real* subprocess (`python -m t4t.cli.main ...`), not
via Typer's in-process CliRunner or a mocked CommandContext -- per the
issue's acceptance criteria, several of these need a real subprocess run:

- run_id must match between the JSON event stream and runs.sqlite for the
  same invocation.
- `t4t run --log-format json | jq` must succeed: every stdout line valid JSON.
- A fake secret in connection config must never appear in captured JSON
  output.

See tests/observability/test_logging_setup.py for formatter/filter unit
tests, and tests/cli/commands/ for the existing (updated) unit tests of
run.py/build.py/test.py argument wiring.
"""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _write_minimal_project(root: Path, *, extra_toml: str = "") -> Path:
    """A tiny 2-model duckdb project: t.b depends on t.a, plus one singular
    SQL test on t.a so `t4t build`/`t4t test` have something to run
    (test_started/test_finished only fire when a model has test metadata)."""
    (root / "models" / "t").mkdir(parents=True)
    (root / "data").mkdir(parents=True)
    (root / "tests").mkdir(parents=True)

    db_path = root / "data" / "e2e.duckdb"
    (root / "project.toml").write_text(
        f"""project_folder = "e2e"
[environments.dev.connection]
type = "duckdb"
path = "{db_path.as_posix()}"
{extra_toml}
""",
        encoding="utf-8",
    )
    (root / "models" / "t" / "a.sql").write_text("SELECT 1 AS id, 'x' AS name\n", encoding="utf-8")
    (root / "models" / "t" / "b.sql").write_text("SELECT * FROM a\n", encoding="utf-8")
    # Companion metadata file attaching a built-in generic test to t.a, the
    # same pattern as examples/t_project/models/my_schema/my_first_table.py
    # -- a bare .sql file has no metadata block of its own. `schema` must be
    # present (even empty) for MetadataExtractor.extract_model_metadata to
    # recognize this as real metadata -- see
    # t4t/engine/metadata/metadata_extractor.py.
    (root / "models" / "t" / "a.py").write_text(
        "from t4t.parser.processing.model_builder import SqlModelMetadata\n"
        "from t4t.typing.metadata import ModelMetadata\n\n"
        'metadata: ModelMetadata = {"schema": [], "tests": ["row_count_gt_0"]}\n'
        "model = SqlModelMetadata(metadata)\n",
        encoding="utf-8",
    )
    return root.resolve()


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return _write_minimal_project(tmp_path / "proj")


def _run_t4t(args: list[str], **env_overrides: str) -> subprocess.CompletedProcess:
    import os

    env = os.environ.copy()
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-m", "t4t.cli.main", *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
        timeout=120,
    )


def _json_lines(stdout: str) -> list[dict]:
    lines = [line for line in stdout.splitlines() if line.strip()]
    parsed = []
    for i, line in enumerate(lines, 1):
        try:
            parsed.append(json.loads(line))
        except json.JSONDecodeError as e:  # pragma: no cover - assertion helper
            pytest.fail(f"stdout line {i} is not valid JSON: {line!r} ({e})")
    return parsed


class TestJSONModeIsValidJSONL:
    """Acceptance criterion: `t4t run --log-format json | jq` succeeds --
    every stdout line is valid JSON."""

    def test_every_stdout_line_is_valid_json(self, project: Path):
        result = _run_t4t(["run", str(project), "--log-format", "json"])
        assert result.returncode == 0, result.stdout + result.stderr

        lines = _json_lines(result.stdout)
        assert len(lines) > 0
        for payload in lines:
            assert "ts" in payload
            assert "level" in payload
            assert "msg" in payload

    def test_t4t_log_format_env_var_also_selects_json(self, project: Path):
        result = _run_t4t(["run", str(project)], T4T_LOG_FORMAT="json")
        assert result.returncode == 0, result.stdout + result.stderr
        lines = _json_lines(result.stdout)
        assert len(lines) > 0


class TestRunIdJoin:
    """Acceptance criterion: the same run_id appears in every JSON event and
    in runs.sqlite for that invocation -- verified at the CLI level."""

    def test_run_id_matches_json_stream_and_runs_sqlite(self, project: Path):
        result = _run_t4t(["run", str(project), "--log-format", "json"])
        assert result.returncode == 0, result.stdout + result.stderr

        lines = _json_lines(result.stdout)
        run_started = [line for line in lines if line.get("type") == "run_started"]
        assert len(run_started) == 1
        run_id = run_started[0]["run_id"]
        assert isinstance(run_id, str) and run_id

        # Every event that carries a run_id must carry the *same* one.
        event_run_ids = {line["run_id"] for line in lines if "run_id" in line}
        assert event_run_ids == {run_id}

        runs_sqlite = project / "output" / "dev" / "runs.sqlite"
        assert runs_sqlite.is_file()
        conn = sqlite3.connect(runs_sqlite)
        try:
            row = conn.execute("select run_id from runs order by rowid desc limit 1").fetchone()
        finally:
            conn.close()
        assert row is not None
        assert row[0] == run_id


class TestSixNamedLifecycleEvents:
    """Design decision 2: exactly the 6 named events, run_started first,
    run_finished last, same run_id throughout."""

    def test_run_emits_run_started_model_events_and_run_finished_in_order(self, project: Path):
        result = _run_t4t(["run", str(project), "--log-format", "json"])
        assert result.returncode == 0, result.stdout + result.stderr

        lines = _json_lines(result.stdout)
        typed = [line for line in lines if "type" in line]
        types_in_order = [line["type"] for line in typed]

        assert types_in_order[0] == "run_started"
        assert types_in_order[-1] == "run_finished"
        assert set(types_in_order) <= {
            "run_started",
            "model_started",
            "model_finished",
            "test_started",
            "test_finished",
            "run_finished",
        }
        # Two models (t.a, t.b) -> one started/finished pair each.
        assert types_in_order.count("model_started") == 2
        assert types_in_order.count("model_finished") == 2
        # Every model_started is immediately paired with its model_finished
        # before the next model_started (real per-model timing, not a batch
        # bookend at the end).
        for i, t in enumerate(types_in_order):
            if t == "model_started":
                assert types_in_order[i + 1] == "model_finished"

    def test_build_also_emits_test_lifecycle_events(self, project: Path):
        result = _run_t4t(["build", str(project), "--log-format", "json"])
        assert result.returncode == 0, result.stdout + result.stderr

        types_in_order = [line["type"] for line in _json_lines(result.stdout) if "type" in line]
        assert "test_started" in types_in_order
        assert "test_finished" in types_in_order
        assert types_in_order[0] == "run_started"
        assert types_in_order[-1] == "run_finished"


class TestRedaction:
    """Design decision 5: a fake secret in connection config must never
    appear in captured JSON log output -- proven, not assumed."""

    def test_fake_secret_never_appears_in_json_output(self, tmp_path: Path):
        secret = "sk-FAKE-SECRET-e2e-99887766"
        proj = _write_minimal_project(tmp_path / "proj", extra_toml=f'password = "{secret}"\n')

        # --verbose so the debug-level "Resolved connection configuration"
        # diagnostic (which carries the *unredacted* config via extra, by
        # design -- the formatter is responsible for redacting it) fires.
        result = _run_t4t(["run", str(proj), "--log-format", "json", "--verbose"])
        assert result.returncode == 0, result.stdout + result.stderr

        assert secret not in result.stdout
        assert secret not in result.stderr

        lines = _json_lines(result.stdout)
        redacted = [line for line in lines if "connection_config" in line]
        assert redacted, "expected the connection_config diagnostic line to be present"
        assert redacted[0]["connection_config"]["password"] == "****"


class TestTextModeNoDebugLeak:
    """Constraint 2 / acceptance criterion: no previously-silent
    logger.debug call sites become newly visible in text mode by default."""

    def test_default_text_mode_has_no_internal_debug_chatter(self, project: Path):
        result = _run_t4t(["run", str(project)])
        assert result.returncode == 0, result.stdout + result.stderr

        # These are real, pre-existing logger.debug/info call sites in
        # engine/adapter modules (not part of t4t's curated CLI output) that
        # must stay off stdout by default -- see
        # t4t.observability.logging_setup.GATED_LOGGER_NAMES /
        # CLI_OUTPUT_LOGGER_NAMES.
        never_on_stdout_by_default = [
            "Starting execution of",  # t4t.engine.executors.model_executor
            "Starting project compilation",  # t4t.compiler
            "Connected to DuckDB database",  # adapter internals
            "Executing model:",  # model_executor debug line
        ]
        for needle in never_on_stdout_by_default:
            assert needle not in result.stdout, f"{needle!r} leaked into default text stdout"

        # ...but the genuinely new, intentional per-model progress lines
        # (this issue's whole point) are there.
        assert "▶ t.a" in result.stdout
        assert "✅ t.a" in result.stdout
        assert "Running t4t on project:" in result.stdout
        assert "Completed!" in result.stdout

    def test_verbose_text_mode_does_not_crash_and_still_only_curated_output(self, project: Path):
        """--verbose enables debug level for t4t's own curated loggers, but
        must not turn on unrelated internal chatter on stdout (still gated
        by the allowlist/marker, not just level)."""
        result = _run_t4t(["run", str(project), "--verbose"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert "Starting execution of" not in result.stdout
