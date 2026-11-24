"""SQLite persistence for session history (stdlib sqlite3, no ORM)."""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session_id_id ON messages(session_id, id);

-- Extra table (allowed by the assignment): the session's system-prompt override.
-- Kept out of `messages` so it never appears in the history endpoint.
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    system_prompt TEXT,
    updated_at TEXT NOT NULL
);
"""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: str) -> None:
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    # ---------- sync implementations (run in a worker thread) ----------

    def _init_schema(self) -> None:
        directory = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(directory, exist_ok=True)
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(SCHEMA)

    def _ping(self) -> bool:
        with self._connect() as conn:
            conn.execute("SELECT 1 FROM messages LIMIT 1").fetchall()
        return True

    def _get_history(self, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT role, content, metadata, created_at FROM messages "
                "WHERE session_id = ? ORDER BY id ASC",
                (session_id,),
            ).fetchall()
        history = []
        for row in rows:
            item: dict[str, Any] = {"role": row["role"], "content": row["content"]}
            if row["role"] == "assistant" and row["metadata"]:
                item["metadata"] = json.loads(row["metadata"])
            item["created_at"] = row["created_at"]
            history.append(item)
        return history

    def _get_system_prompt(self, session_id: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT system_prompt FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        return row["system_prompt"] if row else None

    def _save_exchange(
        self,
        session_id: str,
        user_content: str,
        assistant_content: str,
        metadata: dict[str, Any],
        system_prompt_override: str | None,
    ) -> None:
        user_ts = utc_now_iso()
        conn = self._connect()
        try:
            with conn:  # one transaction: both rows or neither
                conn.execute(
                    "INSERT INTO messages (session_id, role, content, metadata, created_at) "
                    "VALUES (?, 'user', ?, NULL, ?)",
                    (session_id, user_content, user_ts),
                )
                conn.execute(
                    "INSERT INTO messages (session_id, role, content, metadata, created_at) "
                    "VALUES (?, 'assistant', ?, ?, ?)",
                    (session_id, assistant_content, json.dumps(metadata), utc_now_iso()),
                )
                if system_prompt_override is not None:
                    conn.execute(
                        "INSERT INTO sessions (session_id, system_prompt, updated_at) VALUES (?, ?, ?) "
                        "ON CONFLICT(session_id) DO UPDATE SET "
                        "system_prompt = excluded.system_prompt, updated_at = excluded.updated_at",
                        (session_id, system_prompt_override, utc_now_iso()),
                    )
        finally:
            conn.close()

    # ---------- async API ----------

    async def init_schema(self) -> None:
        await asyncio.to_thread(self._init_schema)

    async def ping(self) -> bool:
        try:
            return await asyncio.to_thread(self._ping)
        except sqlite3.Error:
            return False

    async def get_history(self, session_id: str) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._get_history, session_id)

    async def get_system_prompt(self, session_id: str) -> str | None:
        return await asyncio.to_thread(self._get_system_prompt, session_id)

    async def save_exchange(self, *args: Any) -> None:
        await asyncio.to_thread(self._save_exchange, *args)
