"""#20 step 3/5: DuckDB warehouse state-table DDL/DML against a real connection.

DuckDB is the one previously-asserted-then-disproven mechanism (#20's
research found `GENERATED ALWAYS AS IDENTITY` unsupported on DuckDB, using
`CREATE SEQUENCE` + `DEFAULT nextval(...)` instead), so it gets a real
in-memory-connection test, not just the adapter-agnostic
`StateTableMixin` unit tests in tests/adapters/test_state_table.py.
"""

from t4t.adapters.base.state_table import STATE_TABLE_NAME


class TestDuckDBStateTableDDL:
    def test_identity_column_not_supported_by_duckdb(self, duckdb_adapter):
        """Sanity check for #20's design decision: DuckDB really does reject
        `GENERATED ALWAYS AS IDENTITY` (this is *why* the DDL below uses
        CREATE SEQUENCE + DEFAULT nextval(...) instead)."""
        import pytest

        with pytest.raises(Exception, match="not implemented|Constraint"):
            duckdb_adapter.connection.execute(
                "CREATE TABLE t_identity_probe (id BIGINT GENERATED ALWAYS AS IDENTITY)"
            )

    def test_ensure_state_table_creates_schema_and_table(self, duckdb_adapter):
        duckdb_adapter.ensure_state_table("analytics")

        schema_row = duckdb_adapter.connection.execute(
            "SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name = ?",
            ["analytics_STATE"],
        ).fetchone()
        assert schema_row[0] == 1

        table_row = duckdb_adapter.connection.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = ? AND table_name = ?",
            ["analytics_STATE", STATE_TABLE_NAME],
        ).fetchone()
        assert table_row[0] == 1

    def test_ensure_state_table_idempotent(self, duckdb_adapter):
        duckdb_adapter.ensure_state_table("analytics")
        duckdb_adapter.ensure_state_table("analytics")  # must not raise

    def test_insert_and_read_latest_run_state(self, duckdb_adapter):
        duckdb_adapter.ensure_state_table("analytics")
        duckdb_adapter.insert_run_state("analytics", "run-1", '{"run_id": "run-1"}')
        duckdb_adapter.insert_run_state("analytics", "run-2", '{"run_id": "run-2"}')

        latest = duckdb_adapter.read_latest_run_state("analytics")
        assert latest == '{"run_id": "run-2"}'

    def test_read_latest_run_state_no_rows_returns_none(self, duckdb_adapter):
        duckdb_adapter.ensure_state_table("analytics")
        assert duckdb_adapter.read_latest_run_state("analytics") is None

    def test_insert_and_read_fingerprint_state(self, duckdb_adapter):
        duckdb_adapter.ensure_state_table("analytics")
        duckdb_adapter.insert_fingerprint_state(
            "analytics", "analytics.orders", "sql1", "cfg1", "fp1", 1
        )

        record = duckdb_adapter.read_fingerprint_state("analytics", "analytics.orders")
        assert record is not None
        assert record["sql_hash"] == "sql1"
        assert record["config_hash"] == "cfg1"
        assert record["fingerprint"] == "fp1"
        assert record["fingerprint_spec_version"] == 1
        assert record["updated_at"] is not None

    def test_fingerprint_state_overwrite_returns_latest_by_ordering_column(self, duckdb_adapter):
        """Insert-only (append-only): a second fingerprint write for the same
        model is a new row, and `read_fingerprint_state` must return the one
        with the higher `id` -- not the first-inserted row, and not
        (necessarily) the one with the latest wall-clock `written_at`, which
        is the whole point of using an ordering column (#20 step 8)."""
        duckdb_adapter.ensure_state_table("analytics")
        duckdb_adapter.insert_fingerprint_state(
            "analytics", "analytics.orders", "sql-old", "cfg-old", "fp-old", 1
        )
        duckdb_adapter.insert_fingerprint_state(
            "analytics", "analytics.orders", "sql-new", "cfg-new", "fp-new", 1
        )

        record = duckdb_adapter.read_fingerprint_state("analytics", "analytics.orders")
        assert record["sql_hash"] == "sql-new"

    def test_read_fingerprint_state_missing_model_returns_none(self, duckdb_adapter):
        duckdb_adapter.ensure_state_table("analytics")
        assert duckdb_adapter.read_fingerprint_state("analytics", "analytics.missing") is None

    def test_ordering_by_id_not_insertion_or_timestamp(self, duckdb_adapter, monkeypatch):
        """#20 step 8 / acceptance criterion 5: rows inserted out of
        wall-clock order still come back ordered by the `id` sequence
        column, not by `written_at`. We fake this by inserting a row with an
        explicit, deliberately-earlier `written_at` *after* a row with a
        later one, then asserting `read_latest_run_state` still returns the
        row with the higher `id` (inserted second), matching #20's explicit
        scope: this proves ordering-column correctness from sequential
        calls, not concurrent-writer safety."""
        duckdb_adapter.ensure_state_table("analytics")
        table = duckdb_adapter.state_table_ref("analytics")

        # Row 1: written_at far in the future.
        duckdb_adapter.connection.execute(
            f"INSERT INTO {table} (record_type, written_at, run_id, manifest_json) "
            "VALUES ('run', TIMESTAMP '2099-01-01 00:00:00', ?, ?)",
            ["run-early-id-future-clock", '{"run_id": "run-early-id-future-clock"}'],
        )
        # Row 2: written_at far in the past, but inserted (and so sequenced) second.
        duckdb_adapter.connection.execute(
            f"INSERT INTO {table} (record_type, written_at, run_id, manifest_json) "
            "VALUES ('run', TIMESTAMP '2000-01-01 00:00:00', ?, ?)",
            ["run-later-id-past-clock", '{"run_id": "run-later-id-past-clock"}'],
        )

        latest = duckdb_adapter.read_latest_run_state("analytics")
        # The `id` sequence column, not `written_at`, decides "latest".
        assert latest == '{"run_id": "run-later-id-past-clock"}'
