"""PostgreSQL drop-in replacement for mem0's SQLiteManager."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import psycopg

logger = logging.getLogger(__name__)


class PostgresHistoryManager:
    def __init__(self, db_url: str):
        self._db_url = db_url
        self._ensure_tables()

    def _conn(self):
        return psycopg.connect(self._db_url)

    def _ensure_tables(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS history (
                    id         TEXT PRIMARY KEY,
                    memory_id  TEXT,
                    old_memory TEXT,
                    new_memory TEXT,
                    event      TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    is_deleted INTEGER DEFAULT 0,
                    actor_id   TEXT,
                    role       TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id            TEXT PRIMARY KEY,
                    session_scope TEXT,
                    role          TEXT,
                    content       TEXT,
                    name          TEXT,
                    created_at    TEXT
                )
            """)
            conn.commit()

    def add_history(
        self,
        memory_id: str,
        old_memory: Optional[str],
        new_memory: Optional[str],
        event: str,
        *,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
        is_deleted: int = 0,
        actor_id: Optional[str] = None,
        role: Optional[str] = None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO history (id, memory_id, old_memory, new_memory, event, "
                "created_at, updated_at, is_deleted, actor_id, role) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (str(uuid.uuid4()), memory_id, old_memory, new_memory, event,
                 created_at, updated_at, is_deleted, actor_id, role),
            )
            conn.commit()

    def batch_add_history(self, records: List[Dict[str, Any]]) -> None:
        with self._conn() as conn:
            conn.executemany(
                "INSERT INTO history (id, memory_id, old_memory, new_memory, event, "
                "created_at, updated_at, is_deleted, actor_id, role) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                [
                    (
                        str(uuid.uuid4()),
                        r.get("memory_id"),
                        r.get("old_memory"),
                        r.get("new_memory"),
                        r.get("event"),
                        r.get("created_at"),
                        r.get("updated_at"),
                        r.get("is_deleted", 0),
                        r.get("actor_id"),
                        r.get("role"),
                    )
                    for r in records
                ],
            )
            conn.commit()

    def get_history(self, memory_id: str) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, memory_id, old_memory, new_memory, event, "
                "created_at, updated_at, is_deleted, actor_id, role "
                "FROM history WHERE memory_id = %s ORDER BY created_at ASC",
                (memory_id,),
            ).fetchall()
        return [
            {
                "id": r[0], "memory_id": r[1], "old_memory": r[2],
                "new_memory": r[3], "event": r[4], "created_at": r[5],
                "updated_at": r[6], "is_deleted": bool(r[7]),
                "actor_id": r[8], "role": r[9],
            }
            for r in rows
        ]

    def save_messages(self, messages: List[Dict[str, Any]], session_scope: str) -> None:
        if not messages:
            return
        with self._conn() as conn:
            now = datetime.now(timezone.utc).isoformat()
            for msg in messages:
                conn.execute(
                    "INSERT INTO messages (id, session_scope, role, content, name, created_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (str(uuid.uuid4()), session_scope, msg.get("role"),
                     msg.get("content"), msg.get("name"), now),
                )
            # Keep only the 10 most recent messages per scope
            conn.execute(
                "DELETE FROM messages WHERE session_scope = %s AND id NOT IN ("
                "  SELECT id FROM messages WHERE session_scope = %s "
                "  ORDER BY created_at DESC LIMIT 10"
                ")",
                (session_scope, session_scope),
            )
            conn.commit()

    def get_last_messages(self, session_scope: str, limit: int = 10) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT role, content, name, created_at FROM ("
                "  SELECT role, content, name, created_at FROM messages "
                "  WHERE session_scope = %s ORDER BY created_at DESC LIMIT %s"
                ") sub ORDER BY created_at ASC",
                (session_scope, limit),
            ).fetchall()
        return [
            {"role": r[0], "content": r[1], "name": r[2], "created_at": r[3]}
            for r in rows
        ]

    def reset(self) -> None:
        with self._conn() as conn:
            conn.execute("TRUNCATE TABLE history")
            conn.execute("TRUNCATE TABLE messages")
            conn.commit()

    def close(self) -> None:
        pass  # connections are opened per-call and closed by the context manager

    def __del__(self):
        self.close()
