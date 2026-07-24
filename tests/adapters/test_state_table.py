"""#20 step 4: permission-denied path for warehouse state-table DDL.

`StateTableMixin.ensure_state_table` must catch a DDL failure (e.g. a
missing CREATE SCHEMA/CREATE TABLE grant) and raise `StateTableDDLError`
with the literal DDL text, rather than letting a raw permission-denied
exception propagate. Uses a minimal fake adapter, not a real connection --
the real-connection DDL runs are covered separately per adapter (DuckDB:
tests/adapters/duckdb/test_state_table_duckdb.py exercises this against a
real in-memory connection).
"""

import pytest

from t4t.adapters.base.state_table import StateTableDDLError, StateTableMixin


class _PermissionDeniedAdapter(StateTableMixin):
    """A fake adapter whose DDL always fails with a permission error."""

    def __init__(self) -> None:
        self.executed: list[str] = []

    def _state_table_ddl_statements(self, data_schema: str) -> list[str]:
        schema = self.state_schema_name(data_schema)
        table = self.state_table_ref(data_schema)
        return [
            f"CREATE SCHEMA IF NOT EXISTS {schema}",
            f"CREATE TABLE IF NOT EXISTS {table} (id BIGINT)",
        ]

    def _execute_state_ddl_statement(self, stmt: str) -> None:
        self.executed.append(stmt)
        raise PermissionError("permission denied for database analytics")


class _FailsOnSecondStatementAdapter(StateTableMixin):
    """First DDL statement succeeds, second (the table) fails."""

    def __init__(self) -> None:
        self.executed: list[str] = []

    def _state_table_ddl_statements(self, data_schema: str) -> list[str]:
        schema = self.state_schema_name(data_schema)
        table = self.state_table_ref(data_schema)
        return [
            f"CREATE SCHEMA IF NOT EXISTS {schema}",
            f"CREATE TABLE IF NOT EXISTS {table} (id BIGINT)",
        ]

    def _execute_state_ddl_statement(self, stmt: str) -> None:
        self.executed.append(stmt)
        if "CREATE TABLE" in stmt:
            raise PermissionError("permission denied for schema analytics_STATE")


class TestStateTableDDLError:
    def test_permission_denied_raises_state_table_ddl_error(self) -> None:
        adapter = _PermissionDeniedAdapter()
        with pytest.raises(StateTableDDLError) as excinfo:
            adapter.ensure_state_table("analytics")

        err = excinfo.value
        assert err.data_schema == "analytics"
        assert isinstance(err.original, PermissionError)

    def test_error_message_includes_literal_ddl_text(self) -> None:
        adapter = _PermissionDeniedAdapter()
        with pytest.raises(StateTableDDLError) as excinfo:
            adapter.ensure_state_table("analytics")

        message = str(excinfo.value)
        assert "CREATE SCHEMA IF NOT EXISTS analytics_STATE" in message
        assert "CREATE TABLE IF NOT EXISTS analytics_STATE.t4t_model_state" in message
        # Not a raw traceback -- the underlying error is summarized, not dumped.
        assert "permission denied" in message

    def test_second_statement_failure_still_reports_all_ddl_text(self) -> None:
        """A partial failure (schema created, table creation denied) must
        still surface the *whole* DDL block -- an admin needs the schema
        creation statement too, to run both from a clean slate."""
        adapter = _FailsOnSecondStatementAdapter()
        with pytest.raises(StateTableDDLError) as excinfo:
            adapter.ensure_state_table("analytics")

        assert adapter.executed == [
            "CREATE SCHEMA IF NOT EXISTS analytics_STATE",
            "CREATE TABLE IF NOT EXISTS analytics_STATE.t4t_model_state (id BIGINT)",
        ]
        message = str(excinfo.value)
        assert "CREATE SCHEMA IF NOT EXISTS analytics_STATE" in message
        assert "CREATE TABLE IF NOT EXISTS analytics_STATE.t4t_model_state" in message

    def test_success_does_not_raise(self) -> None:
        class _SucceedsAdapter(StateTableMixin):
            def __init__(self) -> None:
                self.executed: list[str] = []

            def _state_table_ddl_statements(self, data_schema: str) -> list[str]:
                return [f"CREATE SCHEMA IF NOT EXISTS {self.state_schema_name(data_schema)}"]

            def _execute_state_ddl_statement(self, stmt: str) -> None:
                self.executed.append(stmt)

        adapter = _SucceedsAdapter()
        adapter.ensure_state_table("analytics")
        assert adapter.executed == ["CREATE SCHEMA IF NOT EXISTS analytics_STATE"]
