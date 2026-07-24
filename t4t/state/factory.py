"""Backend selection: local (default) vs warehouse (#20 step 6).

A single entry point used by every call site that used to construct
``LocalStateBackend`` directly (``t4t/executor.py``, ``t4t/state/retry.py``)
so ``environments.<env>.state.backend`` is the *only* thing that changes
which backend a given (project, environment) pair gets -- omitting the
config, or setting it to ``"local"``, is required to produce byte-for-byte
the same ``LocalStateBackend`` construction as before this module existed
(see ``tests/state/test_factory.py``'s regression-safety tests).
"""

from pathlib import Path
from typing import Any

from t4t.adapters.base import AdapterConfig
from t4t.engine.config import get_state_backend_name
from t4t.state.backend import LocalStateBackend, StateBackend
from t4t.state.warehouse_backend import WarehouseStateBackend


def create_state_backend(
    project_folder: str | Path,
    connection_config: AdapterConfig | dict[str, Any],
    env_name: str | None = None,
) -> StateBackend:
    """Construct the ``StateBackend`` for a (project, environment) pair.

    Reads ``environments.<env>.state.backend`` from ``project.toml``
    (``"local"`` if omitted -- see ``get_state_backend_name``). ``"warehouse"``
    constructs a ``WarehouseStateBackend`` using *connection_config* (the
    same connection the environment's models already use -- no separate
    credentials); anything else constructs the existing ``LocalStateBackend``
    under ``<project_folder>/output``.
    """
    backend_name = get_state_backend_name(project_folder, env_name)
    if backend_name == "warehouse":
        return WarehouseStateBackend(connection_config, env_name=env_name)
    return LocalStateBackend(Path(project_folder) / "output", env_name=env_name)
