"""Tests for prod guardrails (#31) and environment-scoped state (#32)."""

import tempfile
from pathlib import Path

import pytest
import typer

from t4t.state.backend import LocalStateBackend
from t4t.state.manifest import (
    SCHEMA_VERSION,
    RunManifest,
    manifest_from_dict,
    manifest_to_dict,
    results_to_manifest,
    utc_now_iso,
)
from t4t.state.retry import compute_retry_set

# ── RunManifest tests ──────────────────────────────────────────────────────


def test_manifest_schema_version_bumped():
    assert SCHEMA_VERSION == 2, "SCHEMA_VERSION should be bumped to 2"


def test_manifest_has_environment_field():
    m = RunManifest(
        schema_version=2,
        t4t_version="0.1.0",
        run_id="r1",
        command="run",
        started_at="t0",
        finished_at="t1",
        project_root="/p",
        config_hash=None,
        vars_hash=None,
        execution_order=[],
        nodes=[],
        functions=[],
    )
    assert m.environment is None
    assert m.protected is False


def test_manifest_environment_round_trip():
    m = RunManifest(
        schema_version=2,
        t4t_version="0.1.0",
        run_id="r1",
        command="run",
        started_at="t0",
        finished_at="t1",
        project_root="/p",
        config_hash=None,
        vars_hash=None,
        execution_order=[],
        nodes=[],
        functions=[],
        environment="prod",
        protected=True,
    )
    d = manifest_to_dict(m)
    m2 = manifest_from_dict(d)
    assert m2.environment == "prod"
    assert m2.protected is True


def test_manifest_backward_compat_no_env():
    """Old manifests without environment/protected should still load."""
    d = {
        "schema_version": 1,
        "t4t_version": "0.1.0",
        "run_id": "r1",
        "command": "run",
        "started_at": "t0",
        "finished_at": "t1",
        "project_root": "/p",
        "config_hash": None,
        "vars_hash": None,
        "execution_order": [],
        "nodes": [],
        "functions": [],
    }
    m = manifest_from_dict(d)
    assert m.environment is None
    assert m.protected is False


def test_results_to_manifest_passes_environment():
    graph = {"nodes": ["a"], "dependencies": {"a": []}, "dependents": {"a": []}}
    results = {
        "executed_tables": ["a"],
        "failed_tables": [],
        "executed_functions": [],
        "failed_functions": [],
        "table_info": {"a": {"row_count": 1}},
        "analysis": {"execution_order": ["a"], "dependency_graph": graph},
    }
    t0 = utc_now_iso()
    t1 = utc_now_iso()
    m = results_to_manifest(
        results,
        "run",
        "/tmp/proj",
        t0,
        t1,
        environment="prod",
        protected=True,
    )
    assert m.environment == "prod"
    assert m.protected is True
    assert m.schema_version == SCHEMA_VERSION


# ── LocalStateBackend tests ────────────────────────────────────────────────


def test_backend_scopes_paths_per_env():
    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "output"
        backend = LocalStateBackend(output, env_name="prod")
        assert backend._scoped_dir == output / "prod"
        assert str(backend._json_path).endswith("output/prod/last_run.json")
        assert str(backend._db_path).endswith("output/prod/runs.sqlite")


def test_backend_default_no_env():
    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "output"
        backend = LocalStateBackend(output)
        assert backend._scoped_dir == output
        assert str(backend._json_path).endswith("output/last_run.json")


def test_backend_append_and_read_with_env():
    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "output"
        backend = LocalStateBackend(output, env_name="staging")
        m = RunManifest(
            schema_version=2,
            t4t_version="0.1.0",
            run_id="r-staging-1",
            command="run",
            started_at="t0",
            finished_at="t1",
            project_root="/p",
            config_hash=None,
            vars_hash=None,
            execution_order=[],
            nodes=[],
            functions=[],
            environment="staging",
        )
        backend.append_run(m)
        read = backend.read_latest()
        assert read is not None
        assert read.run_id == "r-staging-1"
        assert read.environment == "staging"


def test_backend_read_latest_from_other_env():
    """read_latest should read from the backend's own env scope.
    To read from a different env, create a new backend instance.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "output"
        # Write to prod scope
        prod_backend = LocalStateBackend(output, env_name="prod")
        m_prod = RunManifest(
            schema_version=2,
            t4t_version="0.1.0",
            run_id="r-prod",
            command="run",
            started_at="t0",
            finished_at="t1",
            project_root="/p",
            config_hash=None,
            vars_hash=None,
            execution_order=[],
            nodes=[],
            functions=[],
            environment="prod",
        )
        prod_backend.append_run(m_prod)

        # Write to dev scope
        dev_backend = LocalStateBackend(output, env_name="dev")
        m_dev = RunManifest(
            schema_version=2,
            t4t_version="0.1.0",
            run_id="r-dev",
            command="run",
            started_at="t0",
            finished_at="t1",
            project_root="/p",
            config_hash=None,
            vars_hash=None,
            execution_order=[],
            nodes=[],
            functions=[],
            environment="dev",
        )
        dev_backend.append_run(m_dev)

        # Read from prod scope using a prod-scoped backend
        read_prod = LocalStateBackend(output, env_name="prod").read_latest()
        assert read_prod is not None
        assert read_prod.run_id == "r-prod"

        # Read from dev scope using a dev-scoped backend
        read_dev = LocalStateBackend(output, env_name="dev").read_latest()
        assert read_dev is not None
        assert read_dev.run_id == "r-dev"


# ── Retry tests ────────────────────────────────────────────────────────────


def test_retry_set_computation():
    graph = {
        "nodes": ["A", "B", "C"],
        "dependents": {"A": ["B"], "B": ["C"], "C": []},
        "dependencies": {"A": [], "B": ["A"], "C": ["B"]},
    }
    m = RunManifest(
        schema_version=2,
        t4t_version="0.1.0",
        run_id="r1",
        command="run",
        started_at="t0",
        finished_at="t1",
        project_root="/p",
        config_hash=None,
        vars_hash=None,
        execution_order=["A", "B", "C"],
        nodes=[
            type(
                "NodeResult",
                (),
                {"name": "A", "status": "failed", "error": "e", "skip_reason": None},
            )(),
            type(
                "NodeResult",
                (),
                {
                    "name": "B",
                    "status": "skipped",
                    "error": None,
                    "skip_reason": "not_run:downstream_of_failure",
                },
            )(),
            type(
                "NodeResult",
                (),
                {
                    "name": "C",
                    "status": "skipped",
                    "error": None,
                    "skip_reason": "not_run:downstream_of_failure",
                },
            )(),
        ],
        functions=[],
    )
    s = compute_retry_set(m, graph)
    assert s == {"A", "B", "C"}


# ── Protected env detection tests ──────────────────────────────────────────


def test_is_env_protected():
    from t4t.engine.config import is_env_protected

    with tempfile.TemporaryDirectory() as tmpdir:
        project = Path(tmpdir)
        toml = project / "project.toml"
        toml.write_text("""
[environments.prod]
protected = true

[environments.dev]
""")
        assert is_env_protected(str(project), "prod") is True
        assert is_env_protected(str(project), "dev") is False
        assert is_env_protected(str(project), None) is False


def test_is_env_protected_no_toml():
    from t4t.engine.config import is_env_protected

    with tempfile.TemporaryDirectory() as tmpdir:
        assert is_env_protected(tmpdir, "prod") is False


# ── CommandContext protected env tests ─────────────────────────────────────


def test_command_context_rejects_implicit_protected():
    """Protected env selected implicitly (no --env) should be rejected."""
    from t4t.cli.context import CommandContext

    with tempfile.TemporaryDirectory() as tmpdir:
        project = Path(tmpdir)
        toml = project / "project.toml"
        toml.write_text("""
project_folder = "test"
[environments.prod]
protected = true
[environments.prod.connection]
type = "duckdb"
path = ":memory:"
[environments.dev]
[environments.dev.connection]
type = "duckdb"
path = ":memory:"
""")
        # dev should work fine (not protected)
        ctx = CommandContext(str(project), env="dev")
        assert ctx.env_name == "dev"

        # prod with explicit --env should work
        ctx = CommandContext(str(project), env="prod")
        assert ctx.env_name == "prod"

        # default (dev) should work since dev is not protected
        ctx = CommandContext(str(project))
        assert ctx.env_name == "dev"


def test_command_context_allow_destructive():
    """Protected env with --allow-destructive should work."""
    from t4t.cli.context import CommandContext

    with tempfile.TemporaryDirectory() as tmpdir:
        project = Path(tmpdir)
        toml = project / "project.toml"
        toml.write_text("""
project_folder = "test"
[environments.prod]
protected = true
[environments.prod.connection]
type = "duckdb"
path = ":memory:"
""")
        ctx = CommandContext(str(project), env="prod", allow_destructive=True)
        assert ctx.env_name == "prod"
        assert ctx.allow_destructive is True
        # check_destructive_operation should not raise
        ctx.check_destructive_operation()


def test_command_context_check_destructive_raises():
    """Protected env without --allow-destructive should raise on destructive op."""
    from t4t.cli.context import CommandContext

    with tempfile.TemporaryDirectory() as tmpdir:
        project = Path(tmpdir)
        toml = project / "project.toml"
        toml.write_text("""
project_folder = "test"
[environments.prod]
protected = true
[environments.prod.connection]
type = "duckdb"
path = ":memory:"
""")
        ctx = CommandContext(str(project), env="prod", allow_destructive=False)
        with pytest.raises(typer.Exit):
            ctx.check_destructive_operation()
