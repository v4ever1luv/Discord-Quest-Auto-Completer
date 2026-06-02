from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

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
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS quest_progress (
                quest_id TEXT PRIMARY KEY,
                task_type TEXT NOT NULL,
                total_slept REAL NOT NULL DEFAULT 0,
                enrolled_at TEXT NOT NULL DEFAULT '',
                timestamp TEXT NOT NULL
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
        self._remove_progress(quest_id)
        self._conn.commit()

    def save_progress(
        self, quest_id: str, task_type: str, total_slept: float, enrolled_at: str
    ) -> None:
        if self._conn is None:
            return
        ts = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._conn.execute(
            "INSERT OR REPLACE INTO quest_progress"
            " (quest_id, task_type, total_slept, enrolled_at, timestamp)"
            " VALUES (?, ?, ?, ?, ?)",
            (quest_id, task_type, total_slept, enrolled_at, ts),
        )
        self._conn.commit()

    def load_progress(self, quest_id: str) -> dict[str, Any] | None:
        if self._conn is None:
            return None
        cur = self._conn.execute(
            "SELECT task_type, total_slept, enrolled_at FROM quest_progress WHERE quest_id = ?",
            (quest_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {"task_type": row[0], "total_slept": row[1], "enrolled_at": row[2]}

    def list_in_progress(self) -> set[str]:
        if self._conn is None:
            return set()
        cur = self._conn.execute("SELECT quest_id FROM quest_progress")
        return {row[0] for row in cur.fetchall()}

    def _remove_progress(self, quest_id: str) -> None:
        if self._conn is None:
            return
        self._conn.execute("DELETE FROM quest_progress WHERE quest_id = ?", (quest_id,))

    def remove_all_progress(self) -> None:
        if self._conn is None:
            return
        self._conn.execute("DELETE FROM quest_progress")
        self._conn.commit()
        log.info("persist.progress_cleared")

    def list_all(self) -> set[str]:
        if self._conn is None:
            return set()
        cur = self._conn.execute("SELECT quest_id FROM completed_quests")
        return {row[0] for row in cur.fetchall()}

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
