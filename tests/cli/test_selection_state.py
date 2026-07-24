"""Unit tests for #14 steps 4-6: definition:changed baseline diff (+
missing-baseline fail-open) and run:failed.

Uses a small in-memory fake `StateBackend` (satisfies the `StateBackend`
Protocol) rather than a real `LocalStateBackend`/sqlite file -- these tests
are about `ModelSelector`'s consumption of #13's fingerprint storage and
#18's run manifest, not about the storage layer itself (already covered by
tests/engine/test_fingerprint.py and tests/state/*).
"""

from pathlib import Path

import pytest

from t4t.cli.selection import ModelSelector, SelectionContextError
from t4t.engine.fingerprint import FINGERPRINT_SPEC_VERSION, compute_project_fingerprints
from t4t.state.fingerprint import StoredFingerprint
from t4t.state.manifest import NodeResult, RunManifest


class FakeStateBackend:
    """Minimal in-memory StateBackend for selection tests."""

    def __init__(self) -> None:
        self._fingerprints: dict[str, StoredFingerprint] = {}
        self._latest: RunManifest | None = None

    def append_run(self, manifest: RunManifest) -> None:
        self._latest = manifest

    def read_latest(self) -> RunManifest | None:
        return self._latest

    def save_fingerprint(
        self,
        model_name: str,
        sql_hash: str,
        config_hash: str,
        fingerprint: str,
        fingerprint_spec_version: int,
    ) -> None:
        self._fingerprints[model_name] = StoredFingerprint(
            model_name=model_name,
            sql_hash=sql_hash,
            config_hash=config_hash,
            fingerprint=fingerprint,
            fingerprint_spec_version=fingerprint_spec_version,
        )

    def read_fingerprint(self, model_name: str) -> StoredFingerprint | None:
        return self._fingerprints.get(model_name)


def _model(path: Path, sql: str) -> dict:
    path.write_text(sql, encoding="utf-8")
    return {
        "model_metadata": {
            "file_path": str(path),
            "function_name": None,
            "metadata": {},
        }
    }


def _manifest(nodes: list[NodeResult]) -> RunManifest:
    return RunManifest(
        schema_version=2,
        t4t_version="0.1.0",
        run_id="r1",
        command="run",
        started_at="t0",
        finished_at="t1",
        project_root="/p",
        config_hash=None,
        vars_hash=None,
        execution_order=[n.name for n in nodes],
        nodes=nodes,
        functions=[],
    )


class TestDefinitionChangedBaselineDiff:
    """Step 4."""

    def _graph(self, deps: dict[str, list[str]]) -> dict:
        order = list(deps.keys())
        return {"execution_order": order, "dependencies": deps, "dependents": {}}

    def test_matching_baseline_not_selected_mismatch_is(self, tmp_path: Path) -> None:
        models = {
            "s.a": _model(tmp_path / "a.sql", "SELECT 1\n"),
            "s.b": _model(tmp_path / "b.sql", "SELECT 2\n"),
        }
        graph = self._graph({"s.a": [], "s.b": []})
        current = compute_project_fingerprints(models, graph)

        backend = FakeStateBackend()
        # Baseline for s.a matches current -> not changed.
        backend.save_fingerprint(
            "s.a",
            current["s.a"].sql_hash,
            current["s.a"].config_hash,
            current["s.a"].fingerprint,
            FINGERPRINT_SPEC_VERSION,
        )
        # Baseline for s.b is stale (different fingerprint) -> changed.
        backend.save_fingerprint(
            "s.b", "old_sql_hash", "old_config_hash", "old_fingerprint", FINGERPRINT_SPEC_VERSION
        )

        selector = ModelSelector(select_patterns=["definition:changed"], state_backend=backend)
        filtered, _ = selector.filter_models(models, graph=graph)

        assert "s.a" not in filtered
        assert "s.b" in filtered

    def test_definition_changed_without_context_raises(self, tmp_path: Path) -> None:
        models = {"s.a": _model(tmp_path / "a.sql", "SELECT 1\n")}
        selector = ModelSelector(select_patterns=["definition:changed"])
        with pytest.raises(SelectionContextError):
            selector.is_selected("s.a", models["s.a"])


class TestMissingBaselineFailOpen:
    """Step 5."""

    def test_empty_baseline_store_selects_all_as_changed(self, tmp_path: Path) -> None:
        models = {
            "s.a": _model(tmp_path / "a.sql", "SELECT 1\n"),
            "s.b": _model(tmp_path / "b.sql", "SELECT 2\n"),
        }
        graph = {
            "execution_order": ["s.a", "s.b"],
            "dependencies": {"s.a": [], "s.b": []},
            "dependents": {},
        }
        backend = FakeStateBackend()  # no fingerprints stored at all

        selector = ModelSelector(select_patterns=["definition:changed"], state_backend=backend)
        filtered, _ = selector.filter_models(models, graph=graph)

        assert set(filtered.keys()) == {"s.a", "s.b"}

    def test_missing_baseline_emits_warning(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The missing-baseline warning is curated CLI output (tagged
        `extra={"cli_output": True}`, see t4t/cli/selection.py and
        GATED_LOGGER_NAMES in t4t/observability/logging_setup.py) -- it is
        deliberately excluded from any *other* root handler (including
        pytest's caplog capture handler, via `_ExcludeCuratedFilter`) to
        avoid double-printing, so it must be asserted on stdout via `capsys`,
        not `caplog`.
        """
        models = {"s.a": _model(tmp_path / "a.sql", "SELECT 1\n")}
        graph = {"execution_order": ["s.a"], "dependencies": {"s.a": []}, "dependents": {}}
        backend = FakeStateBackend()

        selector = ModelSelector(
            select_patterns=["definition:changed"], state_backend=backend, env_name="dev"
        )
        selector.filter_models(models, graph=graph)

        out = capsys.readouterr().out
        assert "baseline" in out.lower()
        assert "dev" in out


class TestRunFailed:
    """Step 6."""

    def test_mixed_statuses_selects_only_failed(self) -> None:
        manifest = _manifest(
            [
                NodeResult(name="s.a", status="success", row_count=1),
                NodeResult(name="s.b", status="failed", error="boom"),
                NodeResult(name="s.c", status="skipped", skip_reason="upstream_failed:s.b"),
            ]
        )
        backend = FakeStateBackend()
        backend.append_run(manifest)

        models = {"s.a": {}, "s.b": {}, "s.c": {}}
        selector = ModelSelector(select_patterns=["run:failed"], state_backend=backend)
        filtered, _ = selector.filter_models(models)

        assert set(filtered.keys()) == {"s.b"}

    def test_no_manifest_selects_nothing(self) -> None:
        backend = FakeStateBackend()
        models = {"s.a": {}}
        selector = ModelSelector(select_patterns=["run:failed"], state_backend=backend)
        filtered, _ = selector.filter_models(models)
        assert filtered == {}

    def test_run_failed_without_context_raises(self) -> None:
        selector = ModelSelector(select_patterns=["run:failed"])
        with pytest.raises(SelectionContextError):
            selector.is_selected("s.a", {})
