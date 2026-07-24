"""Storage schema for per-model definition fingerprints.

A ``StoredFingerprint`` holds the three separate hash fields #13 persists per
model per environment: ``sql_hash`` (canonical-AST hash of the model's own
source), ``config_hash`` (hash of its materialization/config metadata), and
``fingerprint`` (the Merkle-style hash-chain combination of the two plus
direct upstream dependency fingerprints). Keeping the three fields separate
-- rather than folding them into one opaque value -- is what lets a future
consumer (e.g. #35's ``t4t plan``) report *why* a model changed.

See ``t4t/engine/fingerprint.py`` for the algorithms that compute these
values, and ``t4t/state/backend.py`` for the ``StateBackend`` Protocol
methods that read/write them.
"""

from dataclasses import dataclass


@dataclass
class StoredFingerprint:
    """A model's persisted fingerprint record."""

    model_name: str
    sql_hash: str
    config_hash: str
    fingerprint: str
    fingerprint_spec_version: int
    updated_at: str | None = None
