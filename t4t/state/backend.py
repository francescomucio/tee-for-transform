"""
Pluggable persistence for run manifests (local JSON + SQLite).
"""

import json
import logging
import sqlite3
from pathlib import Path
from typing import Protocol, runtime_checkable

from t4t.parser.shared.constants import OUTPUT_FILES
from t4t.state.manifest import RunManifest, manifest_from_dict, manifest_to_dict

logger = logging.getLogger(__name__)

SQLITE_NAME = OUTPUT_FILES.get("runs_db", "runs.sqlite")
JSON_NAME = OUTPUT_FILES.get("last_run", "last_run.json")

SCHEMA_USER_VERSION = 1


@runtime_checkable
class StateBackend(Protocol):
    def append_run(self, manifest: RunManifest) -> None: ...
    def read_latest(self, env_name: str | None = None) -> RunManifest | None: ...


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

    def read_latest(self, env_name: str | None = None) -> RunManifest | None:
        """Read the latest run manifest, optionally from a specific environment scope.

        If *env_name* is provided, reads from ``output/<env_name>/`` instead of
        the default scoped path. This allows reading manifests from other
        environments without re-creating the backend.
        """
        json_path: Path
        db_path: Path
        if env_name is not None:
            json_path = self.output_dir / env_name / JSON_NAME
            db_path = self.output_dir / env_name / SQLITE_NAME
        else:
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
