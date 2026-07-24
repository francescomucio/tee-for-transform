"""Model definition fingerprints (#13).

A fingerprint is a stable hash of a model's *definition* -- its own source
plus, transitively, the definitions of everything it depends on -- computed
independently of whether the model's last run succeeded. It is the
foundation #14 (``definition:changed`` selection), #35 (``t4t plan``), and
Slim CI (#11) build on.

Three values are computed and stored per model (see
``t4t/state/fingerprint.py``):

- ``sql_hash``: canonical-AST hash of the model's own source (SQL or
  Python), read directly from disk.
- ``config_hash``: hash of the model's config/materialization metadata.
- ``fingerprint``: a Merkle-style hash chain combining ``sql_hash``,
  ``config_hash``, the fingerprints of direct upstream dependencies, and (for
  Python models) the content hashes of any project-local files imported as a
  side effect of executing the model.

Every function here is pure -- no database connection, no adapter argument
-- so it can run during ``t4t plan`` (#35) without touching data, per the
issue's constraint 2.

Known v1 limitations (documented, not fixed here -- see
docs/user-guide/fingerprinting.md):

- ``SELECT *`` models are fingerprinted at the whole-query level; column-level
  impact requires schema introspection (M4/#38).
- Python source hashing is whole-file: editing one model in a Python file
  that defines several models (e.g. via a loop) marks all of them changed.
- Shared-import detection (constraint 7) only applies to Python models.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import sqlglot

from t4t.state.backend import StateBackend
from t4t.state.fingerprint import StoredFingerprint

logger = logging.getLogger(__name__)

# Bumped whenever the hash algorithm or its inputs change. A stored
# fingerprint whose fingerprint_spec_version doesn't match this is not a
# migration problem -- it's treated as "no baseline" (fail open), same as
# #14's first-run case. See `read_valid_fingerprint` below.
FINGERPRINT_SPEC_VERSION = 1


class FingerprintError(Exception):
    """Raised when a model cannot be fingerprinted (e.g. no source file)."""


def _read_source_file(file_path: str | Path | None, model_name: str) -> str:
    """Read a model's own source file from disk.

    Deliberately reads the raw file, not `resolved_sql`/`original_sql` --
    those are produced *after* `--vars` substitution
    (`substitute_sql_variables` in orchestrator.py runs before parsing), so
    hashing them would make the fingerprint vary run-to-run with `--vars`
    alone, defeating change detection on exactly the projects most likely to
    use `@variable` syntax.
    """
    if file_path is None:
        raise FingerprintError(
            f"Cannot fingerprint model '{model_name}': no source file "
            "(file_path is None). This happens for models not parsed "
            "through the normal project-file path."
        )
    path = Path(file_path)
    try:
        return path.read_text(encoding="utf-8")
    except OSError as e:
        raise FingerprintError(
            f"Cannot fingerprint model '{model_name}': could not read source file {path}: {e}"
        ) from e


def compute_sql_hash_for_sql_model(file_path: str | Path | None, model_name: str = "") -> str:
    """Canonical-AST hash of a SQL model's own source, read from disk.

    Parses with sqlglot and re-serializes with `normalize=True,
    comments=False` before hashing -- both kwargs are required together:
    `normalize=True` alone reformats comments but does not strip them
    (verified empirically during #13's design review). Whitespace
    reformatting and comment edits therefore do not change the hash; logic
    changes do.
    """
    content = _read_source_file(file_path, model_name)
    try:
        parsed = sqlglot.parse_one(content)
    except Exception as e:
        raise FingerprintError(
            f"Cannot fingerprint model '{model_name}': failed to parse SQL from {file_path}: {e}"
        ) from e
    if parsed is None:
        raise FingerprintError(
            f"Cannot fingerprint model '{model_name}': sqlglot could not parse {file_path}"
        )
    canonical = parsed.sql(normalize=True, comments=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_sql_hash_for_python_model(file_path: str | Path | None, model_name: str = "") -> str:
    """Whole-file source hash of a Python model's own source, read from disk.

    v1 limitation, documented not fixed: this hashes the *entire* file, so
    editing any model (or unrelated code) in a Python file that defines
    multiple models marks all of them as changed. Precise per-function
    hashing (`inspect.getsource()` on the specific decorated function) is a
    natural follow-up once this coarser version is proven.
    """
    content = _read_source_file(file_path, model_name)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def compute_config_hash(config: dict[str, Any] | None) -> str:
    """Hash a model's config/materialization metadata.

    Same algorithm as `StateManager.compute_config_hash` (JSON-serialize
    with sorted keys, then sha256) but reimplemented as a pure function here
    so fingerprinting never needs a `StateManager`/DB connection.
    """
    if not config:
        return hashlib.sha256(b"").hexdigest()
    config_str = json.dumps(config, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(config_str.encode("utf-8")).hexdigest()


def hash_file_contents(file_path: str | Path) -> str:
    """sha256 of a file's raw contents, read fresh from disk."""
    path = Path(file_path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_python_model(model_data: dict[str, Any]) -> bool:
    metadata = model_data.get("model_metadata") or {}
    return bool(metadata.get("function_name"))


def compute_model_sql_hash(model_data: dict[str, Any], model_name: str = "") -> str:
    """Dispatch to the SQL or Python source-hash function for this model."""
    metadata = model_data.get("model_metadata") or {}
    file_path = metadata.get("file_path")
    if _is_python_model(model_data):
        return compute_sql_hash_for_python_model(file_path, model_name)
    return compute_sql_hash_for_sql_model(file_path, model_name)


def model_config_dict(model_data: dict[str, Any]) -> dict[str, Any]:
    """Extract the config-relevant metadata dict used for `config_hash`.

    This is `model_metadata.metadata` -- the same dict
    `StateChecker.generate_config_hash` already hashes today (materialization,
    incremental config, schema, tests, partitions, etc.) -- kept as the
    single definition of "config" for a model across both call sites.
    """
    metadata = model_data.get("model_metadata") or {}
    config = metadata.get("metadata") or {}
    return config if isinstance(config, dict) else {}


def shared_import_file_paths(model_data: dict[str, Any]) -> list[str]:
    """Project-local files a Python model imported as a side effect of exec
    (constraint 7), populated by `python_parser.py` via `SharedImportTracker`.
    Empty for SQL models and for Python models with no shared imports."""
    metadata = model_data.get("model_metadata") or {}
    return list(metadata.get("shared_import_files") or [])


def combine_fingerprint(
    sql_hash: str,
    config_hash: str,
    dependency_fingerprints: list[str],
    shared_import_hashes: list[str] | None = None,
) -> str:
    """Merkle-style hash chain: `fingerprint(model) = hash(sql_hash,
    config_hash, [fingerprint(dep) for dep in DIRECT upstream deps])`,
    plus (Python models only) shared-import file hashes.

    Dependency and shared-import hashes are sorted before combining so the
    result doesn't depend on graph/traversal ordering -- only on the actual
    set of values.
    """
    payload = {
        "sql_hash": sql_hash,
        "config_hash": config_hash,
        "dependency_fingerprints": sorted(dependency_fingerprints),
        "shared_import_hashes": sorted(shared_import_hashes or []),
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def compute_project_fingerprints(
    parsed_models: dict[str, Any],
    graph: dict[str, Any],
) -> dict[str, StoredFingerprint]:
    """Compute sql_hash/config_hash/fingerprint for every model in the project.

    Traverses `graph["execution_order"]` (already a topological sort from
    `ProjectParser.get_execution_order()` / `ParserOrchestrator
    .get_execution_order()`) bottom-up so each model's direct-dependency
    fingerprints are already computed by the time it's this model's turn --
    transitivity is automatic, nothing is re-hashed. Entries in the
    execution order that aren't in `parsed_models` (functions, tests) are
    skipped -- fingerprinting is scoped to models only, per the issue's
    design.

    Does not write anything to a StateBackend -- see
    `store_project_fingerprints` for that.
    """
    execution_order: list[str] = list(graph.get("execution_order") or [])
    dependencies: dict[str, list[str]] = graph.get("dependencies") or {}

    fingerprints: dict[str, StoredFingerprint] = {}
    for name in execution_order:
        if name not in parsed_models:
            continue
        model_data = parsed_models[name]

        try:
            sql_hash = compute_model_sql_hash(model_data, model_name=name)
        except FingerprintError as e:
            # One model's source being unreadable/unhashable must not block
            # fingerprinting the rest of the project -- skip it (and, via the
            # `d in fingerprints` filter below, anything downstream simply
            # doesn't get a contribution from it) and keep going.
            logger.warning("Skipping fingerprint for model %s: %s", name, e)
            continue

        config_hash = compute_config_hash(model_config_dict(model_data))

        direct_deps = [d for d in dependencies.get(name, []) if d in fingerprints]
        dep_fingerprints = [fingerprints[d].fingerprint for d in direct_deps]

        shared_import_hashes: list[str] = []
        for shared_path in shared_import_file_paths(model_data):
            try:
                shared_import_hashes.append(hash_file_contents(shared_path))
            except OSError as e:
                logger.warning(
                    "Could not hash shared import file %s for model %s: %s",
                    shared_path,
                    name,
                    e,
                )

        fp = combine_fingerprint(sql_hash, config_hash, dep_fingerprints, shared_import_hashes)

        fingerprints[name] = StoredFingerprint(
            model_name=name,
            sql_hash=sql_hash,
            config_hash=config_hash,
            fingerprint=fp,
            fingerprint_spec_version=FINGERPRINT_SPEC_VERSION,
        )

    return fingerprints


def store_project_fingerprints(
    backend: StateBackend,
    fingerprints: dict[str, StoredFingerprint],
    model_names: set[str] | None = None,
) -> None:
    """Persist fingerprints via a StateBackend.

    If `model_names` is given, only those models are written (used to scope
    writes to models that were actually attempted in a run -- see
    `executor.py`'s `_try_persist_run_manifest`); otherwise all computed
    fingerprints are written.
    """
    for name, fp in fingerprints.items():
        if model_names is not None and name not in model_names:
            continue
        backend.save_fingerprint(
            model_name=fp.model_name,
            sql_hash=fp.sql_hash,
            config_hash=fp.config_hash,
            fingerprint=fp.fingerprint,
            fingerprint_spec_version=fp.fingerprint_spec_version,
        )


def read_valid_fingerprint(backend: StateBackend, model_name: str) -> StoredFingerprint | None:
    """Read a model's stored fingerprint, treating a spec-version mismatch as
    "no baseline" rather than a migration problem (constraint 5).

    A raw-text sha256 (or any older algorithm) cannot be converted into the
    current canonical-AST hash, so there is nothing to migrate: when the
    stored `fingerprint_spec_version` doesn't match `FINGERPRINT_SPEC_VERSION`,
    this returns None (fail open) with a warning, same as #14's first-run
    case (no baseline -> select as changed).
    """
    stored = backend.read_fingerprint(model_name)
    if stored is None:
        return None
    if stored.fingerprint_spec_version != FINGERPRINT_SPEC_VERSION:
        logger.warning(
            "Stored fingerprint for %s uses spec version %s, current is %s; "
            "treating as no baseline.",
            model_name,
            stored.fingerprint_spec_version,
            FINGERPRINT_SPEC_VERSION,
        )
        return None
    return stored
