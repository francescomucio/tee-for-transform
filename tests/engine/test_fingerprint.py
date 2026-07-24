"""Unit tests for #13's fingerprint algorithm (t4t/engine/fingerprint.py).

Organized by implementation step (see the issue's "Implementation steps
(ordered)" section):

- Step 3: SQL canonical-hash function.
- Step 4: Python-model source-hash function.
- Step 6: hash-chain (fingerprint) composition.
- Step 8: fingerprint_spec_version / "no baseline" fallback.

Step 5 (shared-import detector) is unit tested separately in
tests/parser/shared/test_import_tracking.py and
tests/parser/parsers/test_python_parser_shared_imports.py, since it lives in
the parser layer. The end-to-end acceptance test (step 9) lives in
tests/cli/test_fingerprint_e2e.py.
"""

from pathlib import Path

import pytest

from t4t.engine.fingerprint import (
    FINGERPRINT_SPEC_VERSION,
    FingerprintError,
    combine_fingerprint,
    compute_config_hash,
    compute_model_sql_hash,
    compute_project_fingerprints,
    compute_source_hash_for_python_model,
    compute_sql_hash_for_sql_model,
    read_valid_fingerprint,
    store_project_fingerprints,
)
from t4t.state.backend import LocalStateBackend
from t4t.state.fingerprint import StoredFingerprint


class TestSqlCanonicalHash:
    """Step 3."""

    def test_whitespace_reformatting_does_not_change_hash(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.sql"
        f1.write_text("SELECT a, b FROM foo WHERE x = 1\n", encoding="utf-8")
        f2 = tmp_path / "b.sql"
        f2.write_text("select   a,\n  b\nfrom foo\nwhere x=1", encoding="utf-8")

        assert compute_sql_hash_for_sql_model(f1) == compute_sql_hash_for_sql_model(f2)

    def test_comment_only_edit_does_not_change_hash(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.sql"
        f1.write_text("SELECT a, b FROM foo -- original comment\n", encoding="utf-8")
        f2 = tmp_path / "b.sql"
        f2.write_text(
            "-- a very different comment\nSELECT a, b FROM foo\n-- and a trailing one\n",
            encoding="utf-8",
        )
        f3 = tmp_path / "c.sql"
        f3.write_text("SELECT a, b FROM foo\n", encoding="utf-8")

        h1 = compute_sql_hash_for_sql_model(f1)
        h2 = compute_sql_hash_for_sql_model(f2)
        h3 = compute_sql_hash_for_sql_model(f3)
        assert h1 == h2 == h3

    def test_logic_change_changes_hash(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.sql"
        f1.write_text("SELECT a, b FROM foo\n", encoding="utf-8")
        f2 = tmp_path / "b.sql"
        f2.write_text("SELECT a, b, c FROM foo\n", encoding="utf-8")

        assert compute_sql_hash_for_sql_model(f1) != compute_sql_hash_for_sql_model(f2)

    def test_none_file_path_raises_clear_error(self) -> None:
        with pytest.raises(FingerprintError, match="no source file"):
            compute_sql_hash_for_sql_model(None, model_name="schema.some_model")

    def test_missing_file_raises_clear_error(self, tmp_path: Path) -> None:
        with pytest.raises(FingerprintError, match="could not read"):
            compute_sql_hash_for_sql_model(tmp_path / "does_not_exist.sql", model_name="m")

    def test_pure_function_no_adapter_argument(self, tmp_path: Path) -> None:
        """Sanity check for constraint 2: callable with just a path, nothing else."""
        f = tmp_path / "a.sql"
        f.write_text("SELECT 1\n", encoding="utf-8")
        # Should not raise / not require any DB or adapter object.
        assert compute_sql_hash_for_sql_model(f)


class TestPythonSourceHash:
    """Step 4."""

    def test_editing_model_function_body_changes_hash(self, tmp_path: Path) -> None:
        f1 = tmp_path / "m.py"
        f1.write_text("@model(table_name='x')\ndef x():\n    return 'SELECT 1'\n", encoding="utf-8")
        f2 = tmp_path / "m2.py"
        f2.write_text("@model(table_name='x')\ndef x():\n    return 'SELECT 2'\n", encoding="utf-8")
        assert compute_source_hash_for_python_model(f1) != compute_source_hash_for_python_model(f2)

    def test_editing_unrelated_function_in_same_file_also_changes_hash(
        self, tmp_path: Path
    ) -> None:
        """v1 documented limitation: whole-file hashing, not per-function."""
        before = (
            "@model(table_name='x')\n"
            "def x():\n"
            "    return 'SELECT 1'\n\n"
            "@model(table_name='y')\n"
            "def y():\n"
            "    return 'SELECT 2'\n"
        )
        after = before.replace("SELECT 2", "SELECT 3")  # only y's body changes
        f1 = tmp_path / "before.py"
        f1.write_text(before, encoding="utf-8")
        f2 = tmp_path / "after.py"
        f2.write_text(after, encoding="utf-8")

        # Both files hash differently -- proving the whole file (including x's
        # untouched definition) is part of the hash, not just y's body.
        assert compute_source_hash_for_python_model(f1) != compute_source_hash_for_python_model(f2)

    def test_identical_content_same_hash(self, tmp_path: Path) -> None:
        content = "@model(table_name='x')\ndef x():\n    return 'SELECT 1'\n"
        f1 = tmp_path / "a.py"
        f1.write_text(content, encoding="utf-8")
        f2 = tmp_path / "b.py"
        f2.write_text(content, encoding="utf-8")
        assert compute_source_hash_for_python_model(f1) == compute_source_hash_for_python_model(f2)

    def test_none_file_path_raises_clear_error(self) -> None:
        with pytest.raises(FingerprintError, match="no source file"):
            compute_source_hash_for_python_model(None, model_name="schema.some_model")


class TestModelDispatch:
    """compute_model_sql_hash dispatches SQL vs. Python models to the right hasher."""

    def test_sql_model_dispatch(self, tmp_path: Path) -> None:
        f = tmp_path / "a.sql"
        f.write_text("SELECT 1\n", encoding="utf-8")
        model_data = {"model_metadata": {"file_path": str(f), "function_name": None}}
        assert compute_model_sql_hash(model_data) == compute_sql_hash_for_sql_model(f)

    def test_python_model_dispatch(self, tmp_path: Path) -> None:
        f = tmp_path / "a.py"
        f.write_text("@model(table_name='x')\ndef x():\n    return 'SELECT 1'\n", encoding="utf-8")
        model_data = {"model_metadata": {"file_path": str(f), "function_name": "x"}}
        assert compute_model_sql_hash(model_data) == compute_source_hash_for_python_model(f)


class TestConfigHash:
    def test_same_config_same_hash(self) -> None:
        c1 = {"materialization": "table", "schema": []}
        c2 = {"schema": [], "materialization": "table"}
        assert compute_config_hash(c1) == compute_config_hash(c2)

    def test_different_config_different_hash(self) -> None:
        c1 = {"materialization": "table"}
        c2 = {"materialization": "view"}
        assert compute_config_hash(c1) != compute_config_hash(c2)

    def test_empty_config_stable(self) -> None:
        assert compute_config_hash({}) == compute_config_hash(None)


class TestHashChain:
    """Step 6: A -> B -> C chain (A upstream of B, B upstream of C)."""

    def _model(self, path: Path, sql: str) -> dict:
        path.write_text(sql, encoding="utf-8")
        return {
            "model_metadata": {
                "file_path": str(path),
                "function_name": None,
                "metadata": {"materialization": "table"},
            }
        }

    def _graph(self) -> dict:
        return {
            "execution_order": ["s.a", "s.b", "s.c"],
            "dependencies": {"s.a": [], "s.b": ["s.a"], "s.c": ["s.b"]},
        }

    def test_changing_a_changes_b_and_c_fingerprint_not_their_own_hashes(
        self, tmp_path: Path
    ) -> None:
        models = {
            "s.a": self._model(tmp_path / "a.sql", "SELECT 1\n"),
            "s.b": self._model(tmp_path / "b.sql", "SELECT * FROM a\n"),
            "s.c": self._model(tmp_path / "c.sql", "SELECT * FROM b\n"),
        }
        graph = self._graph()
        before = compute_project_fingerprints(models, graph)

        # Change only A's logic.
        (tmp_path / "a.sql").write_text("SELECT 2\n", encoding="utf-8")
        after = compute_project_fingerprints(models, graph)

        assert before["s.a"].sql_hash != after["s.a"].sql_hash
        assert before["s.a"].fingerprint != after["s.a"].fingerprint

        # B and C's own sql_hash/config_hash are unaffected...
        assert before["s.b"].sql_hash == after["s.b"].sql_hash
        assert before["s.b"].config_hash == after["s.b"].config_hash
        assert before["s.c"].sql_hash == after["s.c"].sql_hash
        assert before["s.c"].config_hash == after["s.c"].config_hash

        # ...but their combined fingerprint changes, via the chain.
        assert before["s.b"].fingerprint != after["s.b"].fingerprint
        assert before["s.c"].fingerprint != after["s.c"].fingerprint

    def test_changing_only_c_does_not_affect_a_or_b(self, tmp_path: Path) -> None:
        models = {
            "s.a": self._model(tmp_path / "a.sql", "SELECT 1\n"),
            "s.b": self._model(tmp_path / "b.sql", "SELECT * FROM a\n"),
            "s.c": self._model(tmp_path / "c.sql", "SELECT * FROM b\n"),
        }
        graph = self._graph()
        before = compute_project_fingerprints(models, graph)

        (tmp_path / "c.sql").write_text("SELECT * FROM b WHERE 1=1\n", encoding="utf-8")
        after = compute_project_fingerprints(models, graph)

        assert before["s.a"].fingerprint == after["s.a"].fingerprint
        assert before["s.b"].fingerprint == after["s.b"].fingerprint
        assert before["s.c"].fingerprint != after["s.c"].fingerprint

    def test_config_only_change_changes_config_hash_and_fingerprint_not_sql_hash(
        self, tmp_path: Path
    ) -> None:
        model = self._model(tmp_path / "a.sql", "SELECT 1\n")
        graph = {"execution_order": ["s.a"], "dependencies": {"s.a": []}}
        before = compute_project_fingerprints({"s.a": model}, graph)

        model["model_metadata"]["metadata"] = {"materialization": "view"}
        after = compute_project_fingerprints({"s.a": model}, graph)

        assert before["s.a"].sql_hash == after["s.a"].sql_hash
        assert before["s.a"].config_hash != after["s.a"].config_hash
        assert before["s.a"].fingerprint != after["s.a"].fingerprint

    def test_unreadable_model_skipped_without_blocking_the_rest(self, tmp_path: Path) -> None:
        """A model with no source file (or an unreadable one) must not
        abort fingerprinting the rest of the project."""
        broken = {
            "model_metadata": {
                "file_path": None,
                "function_name": None,
                "metadata": {},
            }
        }
        models = {
            "s.broken": broken,
            "s.a": self._model(tmp_path / "a.sql", "SELECT 1\n"),
        }
        graph = {
            "execution_order": ["s.broken", "s.a"],
            "dependencies": {"s.broken": [], "s.a": []},
        }
        result = compute_project_fingerprints(models, graph)
        assert "s.broken" not in result
        assert "s.a" in result

    def test_unrelated_model_elsewhere_unaffected(self, tmp_path: Path) -> None:
        models = {
            "s.a": self._model(tmp_path / "a.sql", "SELECT 1\n"),
            "s.unrelated": self._model(tmp_path / "u.sql", "SELECT 99\n"),
        }
        graph = {
            "execution_order": ["s.a", "s.unrelated"],
            "dependencies": {"s.a": [], "s.unrelated": []},
        }
        before = compute_project_fingerprints(models, graph)
        (tmp_path / "a.sql").write_text("SELECT 100\n", encoding="utf-8")
        after = compute_project_fingerprints(models, graph)

        assert before["s.unrelated"].sql_hash == after["s.unrelated"].sql_hash
        assert before["s.unrelated"].config_hash == after["s.unrelated"].config_hash
        assert before["s.unrelated"].fingerprint == after["s.unrelated"].fingerprint

    def test_functions_and_tests_in_execution_order_are_skipped(self, tmp_path: Path) -> None:
        models = {"s.a": self._model(tmp_path / "a.sql", "SELECT 1\n")}
        graph = {
            "execution_order": ["s.a", "test:s.a.not_null", "s.some_function"],
            "dependencies": {"s.a": []},
        }
        # Should not raise despite non-model names in execution_order.
        result = compute_project_fingerprints(models, graph)
        assert set(result.keys()) == {"s.a"}

    def test_dependency_order_does_not_affect_fingerprint(self, tmp_path: Path) -> None:
        """combine_fingerprint sorts dependency fingerprints, so declaration
        order in the graph must not matter."""
        f1, f2 = "aaa-fingerprint", "bbb-fingerprint"
        assert combine_fingerprint("s", "c", [f1, f2]) == combine_fingerprint("s", "c", [f2, f1])


class TestStoreProjectFingerprints:
    def test_writes_only_attempted_models(self, tmp_path: Path) -> None:
        backend = LocalStateBackend(tmp_path / "output", env_name="dev")
        fingerprints = {
            "s.a": StoredFingerprint("s.a", "sh", "ch", "fp-a", FINGERPRINT_SPEC_VERSION),
            "s.b": StoredFingerprint("s.b", "sh", "ch", "fp-b", FINGERPRINT_SPEC_VERSION),
        }
        store_project_fingerprints(backend, fingerprints, model_names={"s.a"})

        assert backend.read_fingerprint("s.a") is not None
        assert backend.read_fingerprint("s.b") is None

    def test_writes_all_when_model_names_not_given(self, tmp_path: Path) -> None:
        backend = LocalStateBackend(tmp_path / "output", env_name="dev")
        fingerprints = {
            "s.a": StoredFingerprint("s.a", "sh", "ch", "fp-a", FINGERPRINT_SPEC_VERSION),
        }
        store_project_fingerprints(backend, fingerprints)
        assert backend.read_fingerprint("s.a") is not None


class TestFingerprintSpecVersionFallback:
    """Step 8: version mismatch = "no baseline", not a migration."""

    def test_matching_version_returns_stored(self, tmp_path: Path) -> None:
        backend = LocalStateBackend(tmp_path / "output", env_name="dev")
        backend.save_fingerprint("s.a", "sh", "ch", "fp", FINGERPRINT_SPEC_VERSION)
        result = read_valid_fingerprint(backend, "s.a")
        assert result is not None
        assert result.fingerprint == "fp"

    def test_mismatched_version_treated_as_no_baseline(self, tmp_path: Path) -> None:
        backend = LocalStateBackend(tmp_path / "output", env_name="dev")
        backend.save_fingerprint("s.a", "sh", "ch", "fp", FINGERPRINT_SPEC_VERSION - 1)
        assert read_valid_fingerprint(backend, "s.a") is None

    def test_no_stored_fingerprint_returns_none(self, tmp_path: Path) -> None:
        backend = LocalStateBackend(tmp_path / "output", env_name="dev")
        assert read_valid_fingerprint(backend, "s.a") is None
