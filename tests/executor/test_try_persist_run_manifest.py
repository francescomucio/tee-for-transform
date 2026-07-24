"""#20 step 4 / acceptance criterion 3: a StateTableDDLError (e.g. missing
CREATE SCHEMA permission under the warehouse backend) must fail the whole
`t4t run`/`t4t build` -- not be swallowed into `_try_persist_run_manifest`'s
usual best-effort "log a warning and continue" handling, which every other
persistence failure still gets (regression safety)."""

from pathlib import Path
from unittest.mock import patch

import pytest

from t4t.adapters.base.state_table import StateTableDDLError
from t4t.executor import _try_persist_run_manifest
from t4t.state.warehouse_backend import WarehouseStateBackend


def _minimal_run_results() -> dict:
    return {
        "executed_tables": ["analytics.a"],
        "failed_tables": [],
        "executed_functions": [],
        "failed_functions": [],
        "table_info": {"analytics.a": {"row_count": 1, "materialization": "table"}},
        "analysis": {
            "execution_order": ["analytics.a"],
            "dependency_graph": {"dependencies": {}},
        },
    }


class TestStateTableDDLErrorPropagates:
    def test_ddl_error_from_ensure_schemas_is_not_swallowed(self, tmp_path: Path) -> None:
        connection_config = {"type": "duckdb", "path": str(tmp_path / "state.duckdb")}

        with (
            patch(
                "t4t.executor.create_state_backend",
                return_value=WarehouseStateBackend(connection_config, env_name="prod"),
            ),
            patch.object(
                WarehouseStateBackend,
                "ensure_schemas_for_models",
                side_effect=StateTableDDLError(
                    "analytics",
                    ["CREATE SCHEMA IF NOT EXISTS analytics_STATE"],
                    PermissionError("nope"),
                ),
            ),
            pytest.raises(StateTableDDLError, match="CREATE SCHEMA IF NOT EXISTS analytics_STATE"),
        ):
            _try_persist_run_manifest(
                str(tmp_path),
                _minimal_run_results(),
                "run",
                "2026-01-01T00:00:00+00:00",
                connection_config=connection_config,
                environment="prod",
                run_id="run-1",
            )

    def test_other_exceptions_still_logged_and_swallowed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Regression safety: a non-DDL failure (e.g. a transient warehouse
        connection error) must keep today's best-effort behavior -- log a
        warning, don't raise, don't fail the run. Asserted via captured
        stdout (t4t's own text-format log handler, installed by the autouse
        `_configure_t4t_logging` fixture) rather than `caplog`, since t4t's
        logging setup routes through its own handler rather than the
        handler `caplog` attaches to."""
        connection_config = {"type": "duckdb", "path": str(tmp_path / "state.duckdb")}

        with (
            patch(
                "t4t.executor.create_state_backend",
                return_value=WarehouseStateBackend(connection_config, env_name="prod"),
            ),
            patch.object(
                WarehouseStateBackend,
                "ensure_schemas_for_models",
                side_effect=RuntimeError("transient connection blip"),
            ),
        ):
            # Must not raise.
            _try_persist_run_manifest(
                str(tmp_path),
                _minimal_run_results(),
                "run",
                "2026-01-01T00:00:00+00:00",
                connection_config=connection_config,
                environment="prod",
                run_id="run-1",
            )
        captured = capsys.readouterr()
        assert "Could not persist run manifest" in captured.out

    def test_local_backend_path_unaffected(self, tmp_path: Path) -> None:
        """No environment -> local backend -> no ensure_schemas_for_models
        call at all (it's a WarehouseStateBackend-only concept); the run
        manifest still persists normally."""
        connection_config = {"type": "duckdb", "path": ":memory:"}
        _try_persist_run_manifest(
            str(tmp_path),
            _minimal_run_results(),
            "run",
            "2026-01-01T00:00:00+00:00",
            connection_config=connection_config,
            run_id="run-1",
        )
        assert (tmp_path / "output" / "last_run.json").is_file()
