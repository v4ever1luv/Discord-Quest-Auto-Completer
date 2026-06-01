from __future__ import annotations

import sqlite3
from pathlib import Path

import structlog
from cryptography.fernet import Fernet, InvalidToken

log = structlog.get_logger(__name__)

DATA_DIR = Path("data")
DB_PATH = DATA_DIR / "tokens.db"


def _get_or_create_key() -> bytes:
    key_file = DATA_DIR / ".encryption_key"
    if key_file.exists():
        return key_file.read_bytes()
    key = Fernet.generate_key()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    key_file.write_bytes(key)
    log.info("token_store.key_generated", path=str(key_file))
    return key


class EncryptedTokenStore:
    def __init__(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._cipher = Fernet(_get_or_create_key())
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> None:
        self._conn = sqlite3.connect(str(DB_PATH))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS tokens (
                user_id TEXT PRIMARY KEY,
                encrypted_token TEXT NOT NULL
            )"""
        )
        log.info("token_store.connected", path=str(DB_PATH))

    def set_token(self, user_id: str, token: str) -> None:
        if self._conn is None:
            return
        encrypted = self._cipher.encrypt(token.encode())
        self._conn.execute(
            "INSERT OR REPLACE INTO tokens (user_id, encrypted_token) VALUES (?, ?)",
            (user_id, encrypted.decode()),
        )
        self._conn.commit()

    def get_token(self, user_id: str) -> str | None:
        if self._conn is None:
            return None
        cur = self._conn.execute(
            "SELECT encrypted_token FROM tokens WHERE user_id = ?",
            (user_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        try:
            return self._cipher.decrypt(row[0].encode()).decode()
        except InvalidToken:
            log.error("token_store.decrypt_failed", user_id=user_id)
            return None

    def remove_token(self, user_id: str) -> bool:
        if self._conn is None:
            return False
        cur = self._conn.execute(
            "DELETE FROM tokens WHERE user_id = ?",
            (user_id,),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def list_users(self) -> list[str]:
        if self._conn is None:
            return []
        cur = self._conn.execute("SELECT user_id FROM tokens")
        return [row[0] for row in cur.fetchall()]

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
