"""
Pluggable persistence for run manifests (local JSON + SQLite).
"""

import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

from t4t.parser.shared.constants import OUTPUT_FILES
from t4t.state.fingerprint import StoredFingerprint
from t4t.state.manifest import RunManifest, manifest_from_dict, manifest_to_dict

logger = logging.getLogger(__name__)

SQLITE_NAME = OUTPUT_FILES.get("runs_db", "runs.sqlite")
JSON_NAME = OUTPUT_FILES.get("last_run", "last_run.json")

# Bumped from 1 -> 2 when the `fingerprints` table was added (#13). Purely
# informational (no gated migration reads it), but kept in step with real
# schema changes.
SCHEMA_USER_VERSION = 2


@runtime_checkable
class StateBackend(Protocol):
    """Pluggable persistence for run manifests and per-model fingerprints.

    Implementations are env-scoped: a single backend instance is constructed
    for one (project, environment) pair, matching how ``LocalStateBackend``
    is already used for run manifests. #20 (remote/pluggable backends) adds
    new implementations of this Protocol -- fingerprint logic and call sites
    must not need to change to support them.
    """

    def append_run(self, manifest: RunManifest) -> None: ...
    def read_latest(self) -> RunManifest | None: ...

    def save_fingerprint(
        self,
        model_name: str,
        sql_hash: str,
        config_hash: str,
        fingerprint: str,
        fingerprint_spec_version: int,
    ) -> None:
        """Persist (or overwrite) a model's fingerprint record."""
        ...

    def read_fingerprint(self, model_name: str) -> StoredFingerprint | None:
        """Read a model's most recently persisted fingerprint record, if any."""
        ...


class LocalStateBackend:
    """Write last_run.json + append to runs.sqlite under output_dir."""

    def __init__(self, output_dir: Path, env_name: str | None = None) -> None:
        self.output_dir = Path(output_dir)
        self.env_name = env_name
        if env_name:
            self._scoped_dir = self.output_dir / env_name
        else:
            self._scoped_dir = self.output_dir
        self._json_path = self._scoped_dir / JSON_NAME
        self._db_path = self._scoped_dir / SQLITE_NAME

    def _ensure_db(self, conn: sqlite3.Connection) -> None:
        conn.execute(f"PRAGMA user_version = {SCHEMA_USER_VERSION}")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL UNIQUE,
                manifest_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fingerprints (
                model_name TEXT PRIMARY KEY,
                sql_hash TEXT NOT NULL,
                config_hash TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                fingerprint_spec_version INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

    def append_run(self, manifest: RunManifest) -> None:
        self._scoped_dir.mkdir(parents=True, exist_ok=True)
        payload = manifest_to_dict(manifest)
        text = json.dumps(payload, indent=2)

        self._json_path.write_text(text, encoding="utf-8")

        conn = sqlite3.connect(self._db_path)
        try:
            self._ensure_db(conn)
            conn.execute(
                "INSERT INTO runs (run_id, manifest_json) VALUES (?, ?)",
                (manifest.run_id, text),
            )
            conn.commit()
        finally:
            conn.close()

    def read_latest(self) -> RunManifest | None:
        """Read the latest run manifest from this backend's scoped path.

        The path is determined by the ``env_name`` passed at construction time:
        ``output/<env_name>/`` if set, otherwise ``output/``.
        """
        json_path = self._json_path
        db_path = self._db_path

        if json_path.is_file():
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                return manifest_from_dict(data)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
                logger.warning("Could not read %s: %s", json_path, e)

        if not db_path.is_file():
            return None

        conn = sqlite3.connect(db_path)
        try:
            cur = conn.execute("SELECT manifest_json FROM runs ORDER BY id DESC LIMIT 1")
            row = cur.fetchone()
            if not row:
                return None
            data = json.loads(row[0])
            return manifest_from_dict(data)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError, sqlite3.Error) as e:
            logger.warning("Could not read latest run from SQLite: %s", e)
            return None
        finally:
            conn.close()

    def save_fingerprint(
        self,
        model_name: str,
        sql_hash: str,
        config_hash: str,
        fingerprint: str,
        fingerprint_spec_version: int,
    ) -> None:
        """Persist (or overwrite) a model's fingerprint record.

        Scoped the same way as run manifests: one ``fingerprints`` table per
        ``output/<env_name>/runs.sqlite`` (or ``output/runs.sqlite`` with no
        env).
        """
        self._scoped_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(UTC).isoformat()

        conn = sqlite3.connect(self._db_path)
        try:
            self._ensure_db(conn)
            conn.execute(
                """
                INSERT INTO fingerprints
                    (model_name, sql_hash, config_hash, fingerprint, fingerprint_spec_version, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(model_name) DO UPDATE SET
                    sql_hash = excluded.sql_hash,
                    config_hash = excluded.config_hash,
                    fingerprint = excluded.fingerprint,
                    fingerprint_spec_version = excluded.fingerprint_spec_version,
                    updated_at = excluded.updated_at
                """,
                (model_name, sql_hash, config_hash, fingerprint, fingerprint_spec_version, now),
            )
            conn.commit()
        finally:
            conn.close()

    def read_fingerprint(self, model_name: str) -> StoredFingerprint | None:
        """Read a model's most recently persisted fingerprint record, if any."""
        if not self._db_path.is_file():
            return None

        conn = sqlite3.connect(self._db_path)
        try:
            cur = conn.execute(
                """
                SELECT model_name, sql_hash, config_hash, fingerprint,
                       fingerprint_spec_version, updated_at
                FROM fingerprints WHERE model_name = ?
                """,
                (model_name,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return StoredFingerprint(
                model_name=row[0],
                sql_hash=row[1],
                config_hash=row[2],
                fingerprint=row[3],
                fingerprint_spec_version=int(row[4]),
                updated_at=row[5],
            )
        except sqlite3.Error as e:
            logger.warning("Could not read fingerprint for %s: %s", model_name, e)
            return None
        finally:
            conn.close()
