"""Shared scaffolding for the warehouse state table (#20).

Each adapter that supports the ``warehouse`` state backend hand-writes its
own DDL (schema/table creation, including the ordering-column mechanism --
``GENERATED ALWAYS AS IDENTITY`` for PostgreSQL/Snowflake, ``CREATE
SEQUENCE`` + ``DEFAULT nextval(...)`` for DuckDB, a ``written_at`` timestamp
fallback for BigQuery) and its own parameterized insert/select methods,
rather than routing this through sqlglot transpilation -- see #20's "DDL
approach" design decision: a handful of fixed system columns, not user SQL.

This module only holds what is genuinely shared: the ``<schema>_STATE``
naming convention and the orchestration/error-wrapping around running the
per-adapter DDL. See ``t4t/state/warehouse_backend.py`` for the
``StateBackend`` Protocol implementation that calls into these adapter
methods.
"""

from typing import Any

STATE_TABLE_NAME = "t4t_model_state"


class StateTableDDLError(Exception):
    """Raised when creating the warehouse state schema/table fails.

    Most commonly this means the connection lacks ``CREATE SCHEMA``/``CREATE
    TABLE`` permission (common in locked-down/governed warehouses). Per #20's
    design decision, this is deliberately *not* a raw permission-denied
    stack trace: the exact DDL text is included so a database admin can run
    it manually, and the whole run fails (see #20's multi-schema
    partial-failure rule) rather than proceeding with partial state
    coverage.
    """

    def __init__(self, data_schema: str, ddl_statements: list[str], original: Exception) -> None:
        self.data_schema = data_schema
        self.ddl_statements = list(ddl_statements)
        self.original = original
        ddl_text = "\n\n".join(self.ddl_statements)
        super().__init__(
            f"Could not create warehouse state schema/table for data schema "
            f"'{data_schema}' ({original.__class__.__name__}: {original}).\n\n"
            "This usually means the connection lacks CREATE SCHEMA/CREATE TABLE "
            "permission. Ask a database admin to run the following DDL manually, "
            "then re-run:\n\n"
            f"{ddl_text}"
        )


class SchemaEnsureError(Exception):
    """Raised when the multi-schema pre-creation guard
    (``WarehouseStateBackend.ensure_schemas_for_models``) fails for a reason
    that is *not* a DDL/permission problem -- e.g. a transient connection
    failure while opening the adapter, before any DDL was even attempted.

    Per #20's design decision, "a run touching multiple data schemas fails
    as a whole if any schema's DDL fails" is not narrowed to permission
    failures only: any failure of the guard means we don't actually know
    whether every touched schema's state table exists, so the run must
    abort rather than continue with unknown/partial state coverage. This is
    the sibling of ``StateTableDDLError`` for that non-DDL case -- callers
    (see ``t4t/executor.py``'s ``_try_persist_run_manifest``) re-raise both
    rather than swallowing either into a best-effort warning.
    """

    def __init__(self, original: Exception) -> None:
        self.original = original
        super().__init__(
            "Could not pre-create the warehouse state schema(s) for this run "
            f"({original.__class__.__name__}: {original}). This was not a "
            "DDL/permission failure -- most likely a transient connection "
            "problem. The run has been aborted rather than proceeding with "
            "unknown/partial state coverage; please retry."
        )


class StateTableMixin:
    """Mixin providing the ``<schema>_STATE.t4t_model_state`` naming
    convention and DDL orchestration shared across adapters.

    Concrete adapters implement:

    - ``_state_table_ddl_statements(data_schema)``: the hand-written
      ``CREATE SCHEMA``/``CREATE SEQUENCE``/``CREATE TABLE`` statements for
      that database.
    - ``_execute_state_ddl_statement(stmt)``: runs one DDL statement using
      the adapter's raw connection (no dialect transpilation).
    - ``insert_run_state``/``read_latest_run_state``/
      ``insert_fingerprint_state``/``read_fingerprint_state``: parameterized
      DML using the adapter's own driver, matching how other adapter methods
      in this codebase already talk to their driver directly (see e.g.
      ``SnowflakeAdapter._execute_with_cursor``).
    """

    STATE_TABLE_NAME = STATE_TABLE_NAME

    def state_schema_name(self, data_schema: str) -> str:
        """The paired state schema for a data schema, e.g. ``analytics`` ->
        ``analytics_STATE``."""
        return f"{data_schema}_STATE"

    def state_table_ref(self, data_schema: str) -> str:
        """Fully-qualified state table name for *data_schema*.

        Overridden by ``BigQueryAdapter`` to include the ``project`` prefix
        BigQuery requires.
        """
        return f"{self.state_schema_name(data_schema)}.{self.STATE_TABLE_NAME}"

    def _state_table_ddl_statements(self, data_schema: str) -> list[str]:
        raise NotImplementedError

    def _execute_state_ddl_statement(self, stmt: str) -> None:
        raise NotImplementedError

    def ensure_state_table(self, data_schema: str) -> None:
        """Create ``<data_schema>_STATE.t4t_model_state`` if it doesn't exist.

        Raises ``StateTableDDLError`` (including the literal DDL text) if
        any statement fails -- most commonly a missing ``CREATE SCHEMA``/
        ``CREATE TABLE`` grant. Callers (see
        ``WarehouseStateBackend._ensure_schemas``) let this propagate so the
        whole run fails rather than proceeding with partial state coverage.
        """
        statements = self._state_table_ddl_statements(data_schema)
        for stmt in statements:
            try:
                self._execute_state_ddl_statement(stmt)
            except Exception as e:
                raise StateTableDDLError(data_schema, statements, e) from e

    # -- DML: implemented per adapter, stubs here document the shape only --

    def insert_run_state(self, data_schema: str, run_id: str, manifest_json: str) -> None:
        raise NotImplementedError

    def read_latest_run_state(self, data_schema: str) -> str | None:
        raise NotImplementedError

    def insert_fingerprint_state(
        self,
        data_schema: str,
        model_name: str,
        sql_hash: str,
        config_hash: str,
        fingerprint: str,
        fingerprint_spec_version: int,
    ) -> None:
        raise NotImplementedError

    def read_fingerprint_state(self, data_schema: str, model_name: str) -> dict[str, Any] | None:
        raise NotImplementedError
