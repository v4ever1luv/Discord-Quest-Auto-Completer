from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import structlog

from ._config import settings

log = structlog.get_logger(__name__)


class StateStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or settings.completed_db
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> None:
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS completed_quests (
                quest_id TEXT PRIMARY KEY,
                completed_at TEXT NOT NULL
            )"""
        )
        log.info("persist.connected", path=str(self.db_path))

    def is_completed(self, quest_id: str) -> bool:
        if self._conn is None:
            return False
        cur = self._conn.execute("SELECT 1 FROM completed_quests WHERE quest_id = ?", (quest_id,))
        return cur.fetchone() is not None

    def mark_completed(self, quest_id: str, completed_at: str = "") -> None:
        if self._conn is None:
            return
        ts = completed_at or time.strftime("%Y-%m-%dT%H:%M:%S.000000+00:00")
        self._conn.execute(
            """INSERT OR IGNORE INTO completed_quests (quest_id, completed_at)
               VALUES (?, ?)""",
            (quest_id, ts),
        )
        self._conn.commit()

    def list_all(self) -> set[str]:
        if self._conn is None:
            return set()
        cur = self._conn.execute("SELECT quest_id FROM completed_quests")
        return {row[0] for row in cur.fetchall()}

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
