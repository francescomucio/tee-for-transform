"""WarehouseStateBackend: warehouse-table-backed pluggable state (#20).

Stores run manifests and per-model fingerprints in the environment's own
warehouse connection -- no separate credentials, no local disk -- so a fresh
CI container (which has no local state at all) still has a real baseline to
compare against for ``--retry`` and #14's ``definition:changed`` selection.

Layout: one shared ``<schema>_STATE.t4t_model_state`` table per *data*
schema (not per model table -- see #20's design decision), holding both
run-manifest rows (``record_type = 'run'``) and per-model fingerprint rows
(``record_type = 'fingerprint'``), auto-created on first use. DDL/DML for
each adapter is hand-written on the adapter class itself (see
``t4t/adapters/base/state_table.py`` and each adapter's "Warehouse state
table (#20)" section) -- this module only orchestrates which schema each
piece of state belongs in and implements the ``StateBackend`` Protocol.
"""

import json
import logging
from typing import Any

from t4t.adapters import AdapterConfig, get_adapter
from t4t.adapters.base.state_table import StateTableDDLError
from t4t.state.fingerprint import StoredFingerprint
from t4t.state.manifest import RunManifest, manifest_from_dict, manifest_to_dict

logger = logging.getLogger(__name__)

__all__ = ["WarehouseStateBackend", "StateTableDDLError"]


def _naming_prefixed(schema: str, adapter: Any) -> str:
    """Apply the environment's ``naming.schema_prefix`` (if configured) to a
    raw schema name -- so ``<schema>_STATE`` gets the same per-environment
    isolation models themselves already get (e.g. sharing one physical
    database across ``dev``/``prod`` via a schema prefix), not a raw,
    environment-blind schema name that would collide across environments."""
    naming = getattr(adapter.config, "naming", None)
    prefix = getattr(naming, "schema_prefix", None) if naming else None
    return f"{prefix}{schema}" if prefix else schema


def _default_data_schema(adapter: Any) -> str:
    """The data schema run-manifest rows are written to: the environment's
    configured default schema (``connection.schema``, falling back to the
    adapter's own default, e.g. DuckDB's ``main``), naming-prefixed."""
    schema = adapter.config.schema or adapter._get_default_schema()
    return _naming_prefixed(schema, adapter)


def _model_data_schema(adapter: Any, model_name: str) -> str:
    """The data schema a model belongs to, derived from its (dotted)
    ``model_name`` -- e.g. ``analytics.orders`` -> ``analytics`` -- with the
    environment's naming strategy applied via ``apply_naming`` (the same
    path model execution itself uses), falling back to the environment's
    default schema for an unqualified model name."""
    physical = adapter.apply_naming(model_name)
    if "." in physical:
        schema, _, _ = physical.rpartition(".")
        return schema
    return _default_data_schema(adapter)


class WarehouseStateBackend:
    """``StateBackend`` Protocol implementation backed by the environment's
    own warehouse connection.

    Mirrors ``LocalStateBackend``'s constructor shape (an env-scoped
    resource handle, not a long-lived open connection) but its storage
    calls are genuinely different: every method opens its own short-lived
    adapter connection, does its work, and disconnects. This matches
    ``LocalStateBackend``'s own existing pattern of opening/closing a
    sqlite3 connection per call (see ``t4t/state/backend.py``) rather than
    introducing a new one -- and avoids holding a warehouse connection open
    for the lifetime of a (potentially long) run.

    Needs no separate credentials: ``connection_config`` is the same
    ``AdapterConfig``/dict the environment's models already connect with.
    """

    def __init__(
        self,
        connection_config: AdapterConfig | dict[str, Any],
        env_name: str | None = None,
    ) -> None:
        self.connection_config = connection_config
        self.env_name = env_name

    def _open_adapter(self) -> Any:
        adapter = get_adapter(self.connection_config)
        adapter.connect()
        return adapter

    # -- Multi-schema partial-failure guard --------------------------------

    def ensure_schemas_for_models(self, model_names: set[str]) -> None:
        """Pre-create every data schema's state table a run touches, in one
        pass, before any state is written for that run.

        Per #20's design decision: if schema/table creation succeeds for one
        data schema and fails for another (different grants on each), the
        WHOLE run must fail -- not just the failed schema -- since writing
        state for some models and not others would make #14's
        ``definition:changed`` silently wrong for exactly the untracked
        models. Calling this up front (before any ``append_run``/
        ``save_fingerprint`` calls) means a failure here happens before any
        write, rather than partway through a per-model loop.

        Raises ``StateTableDDLError`` (left uncaught -- callers should let
        it propagate and fail the run) on the first schema that can't be
        created.
        """
        adapter = self._open_adapter()
        try:
            schemas = {_default_data_schema(adapter)}
            schemas.update(_model_data_schema(adapter, name) for name in model_names)
            for schema in sorted(schemas):
                adapter.ensure_state_table(schema)
        finally:
            adapter.disconnect()

    # -- StateBackend Protocol ----------------------------------------------

    def append_run(self, manifest: RunManifest) -> None:
        payload = json.dumps(manifest_to_dict(manifest))
        adapter = self._open_adapter()
        try:
            schema = _default_data_schema(adapter)
            adapter.ensure_state_table(schema)
            adapter.insert_run_state(schema, manifest.run_id, payload)
        finally:
            adapter.disconnect()

    def read_latest(self) -> RunManifest | None:
        adapter = self._open_adapter()
        try:
            schema = _default_data_schema(adapter)
            adapter.ensure_state_table(schema)
            payload = adapter.read_latest_run_state(schema)
        finally:
            adapter.disconnect()

        if payload is None:
            return None
        try:
            return manifest_from_dict(json.loads(payload))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            logger.warning("Could not parse latest warehouse run manifest: %s", e)
            return None

    def save_fingerprint(
        self,
        model_name: str,
        sql_hash: str,
        config_hash: str,
        fingerprint: str,
        fingerprint_spec_version: int,
    ) -> None:
        adapter = self._open_adapter()
        try:
            schema = _model_data_schema(adapter, model_name)
            adapter.ensure_state_table(schema)
            adapter.insert_fingerprint_state(
                schema, model_name, sql_hash, config_hash, fingerprint, fingerprint_spec_version
            )
        finally:
            adapter.disconnect()

    def read_fingerprint(self, model_name: str) -> StoredFingerprint | None:
        adapter = self._open_adapter()
        try:
            schema = _model_data_schema(adapter, model_name)
            adapter.ensure_state_table(schema)
            row = adapter.read_fingerprint_state(schema, model_name)
        finally:
            adapter.disconnect()

        if row is None:
            return None
        return StoredFingerprint(
            model_name=model_name,
            sql_hash=row["sql_hash"],
            config_hash=row["config_hash"],
            fingerprint=row["fingerprint"],
            fingerprint_spec_version=int(row["fingerprint_spec_version"]),
            updated_at=row.get("updated_at"),
        )
