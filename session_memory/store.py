import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union

from session_memory.models import SessionRecord, WorkItemRecord


class SessionStore:
    def __init__(self, db_path: Union[str, Path]):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def _connection(self):
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    jsonl_path TEXT NOT NULL,
                    html_path TEXT NOT NULL,
                    cwd TEXT NOT NULL DEFAULT '',
                    started_at TEXT NOT NULL,
                    ended_at TEXT NOT NULL,
                    message_count INTEGER NOT NULL DEFAULT 0,
                    summary TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    role TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    text TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS work_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    project TEXT NOT NULL DEFAULT '',
                    topic TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'mentioned',
                    summary TEXT NOT NULL DEFAULT '',
                    implemented TEXT NOT NULL DEFAULT '[]',
                    pending TEXT NOT NULL DEFAULT '[]',
                    files TEXT NOT NULL DEFAULT '[]',
                    evidence_message_ordinals TEXT NOT NULL DEFAULT '[]',
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts
                USING fts5(session_id, role, text, content='');
                """
            )

    def upsert_session(self, record: SessionRecord) -> None:
        updated_at = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        started_at = record.started_at or ""
        ended_at = record.ended_at or started_at

        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO sessions (
                    session_id, source, jsonl_path, html_path, cwd, started_at,
                    ended_at, message_count, summary, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    source = excluded.source,
                    jsonl_path = excluded.jsonl_path,
                    html_path = excluded.html_path,
                    cwd = excluded.cwd,
                    started_at = excluded.started_at,
                    ended_at = excluded.ended_at,
                    message_count = excluded.message_count,
                    summary = excluded.summary,
                    updated_at = excluded.updated_at
                """,
                (
                    record.session_id,
                    record.source,
                    record.jsonl_path,
                    record.html_path,
                    record.cwd,
                    started_at,
                    ended_at,
                    len(record.messages),
                    record.summary,
                    updated_at,
                ),
            )
            conn.execute("DELETE FROM messages WHERE session_id = ?", (record.session_id,))
            conn.execute("DELETE FROM messages_fts WHERE session_id = ?", (record.session_id,))
            conn.execute("DELETE FROM work_items WHERE session_id = ?", (record.session_id,))

            for message in record.messages:
                conn.execute(
                    """
                    INSERT INTO messages (session_id, source, role, timestamp, text, ordinal)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.session_id,
                        record.source,
                        message.role,
                        message.timestamp,
                        message.text,
                        message.ordinal,
                    ),
                )
                conn.execute(
                    "INSERT INTO messages_fts (session_id, role, text) VALUES (?, ?, ?)",
                    (record.session_id, message.role, message.text),
                )

            for item in record.work_items:
                self._insert_work_item(conn, record.session_id, item)

    def search_messages(
        self,
        query: str,
        limit: int = 10,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        terms = _query_terms(query)
        if terms:
            rows = self._search_messages_fts(terms, limit=limit, start=start, end=end)
            if rows:
                return rows
        return self._search_messages_like(terms, limit=limit, start=start, end=end)

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            session = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if not session:
                return None
            messages = conn.execute(
                """
                SELECT role, timestamp, text, ordinal
                FROM messages
                WHERE session_id = ?
                ORDER BY ordinal ASC
                """,
                (session_id,),
            ).fetchall()
            work_items = conn.execute(
                """
                SELECT *
                FROM work_items
                WHERE session_id = ?
                ORDER BY id ASC
                """,
                (session_id,),
            ).fetchall()
        payload = dict(session)
        payload["messages"] = [dict(row) for row in messages]
        payload["work_items"] = [self._decode_work_item(dict(row)) for row in work_items]
        return payload

    def find_work_items(
        self,
        project: str = "",
        topic: str = "",
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        clauses = []
        params: List[Any] = []
        if project:
            clauses.append("project LIKE ?")
            params.append("%{}%".format(project))
        if topic:
            clauses.append("topic LIKE ?")
            params.append("%{}%".format(topic))
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(limit)
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT w.*, s.html_path, s.started_at, s.ended_at, s.source
                FROM work_items w
                JOIN sessions s ON s.session_id = w.session_id
                {where}
                ORDER BY s.ended_at DESC
                LIMIT ?
                """.format(where=where),
                params,
            ).fetchall()
        return [self._decode_work_item(dict(row)) for row in rows]

    def _search_messages_fts(
        self,
        terms: Sequence[str],
        limit: int,
        start: Optional[str],
        end: Optional[str],
    ) -> List[Dict[str, Any]]:
        where, params = self._time_clause(start, end, prefix="m")
        match_query = " AND ".join("{}*".format(term) for term in terms)
        params = [match_query] + params + [limit]
        try:
            with self._connection() as conn:
                rows = conn.execute(
                    """
                    SELECT
                        s.session_id, s.source, s.html_path, s.cwd, s.started_at,
                        s.ended_at, s.summary, f.role, m.timestamp, m.ordinal,
                        m.text, snippet(messages_fts, 2, '[', ']', '...', 18) AS snippet
                    FROM messages_fts f
                    JOIN sessions s ON s.session_id = f.session_id
                    JOIN messages m ON m.session_id = f.session_id
                        AND m.role = f.role
                        AND m.text = f.text
                    WHERE messages_fts MATCH ? {where}
                    ORDER BY m.timestamp DESC, m.ordinal DESC
                    LIMIT ?
                    """.format(where=where),
                    params,
                ).fetchall()
        except sqlite3.OperationalError:
            return []
        return [dict(row) for row in rows]

    def _search_messages_like(
        self,
        terms: Sequence[str],
        limit: int,
        start: Optional[str],
        end: Optional[str],
    ) -> List[Dict[str, Any]]:
        where, params = self._time_clause(start, end, prefix="m")
        if where.startswith("AND "):
            where = "WHERE " + where[4:]
        clauses = []
        for term in terms:
            clauses.append("LOWER(m.text) LIKE ?")
            params.append("%{}%".format(term.lower()))
        if clauses:
            where += " AND " + " AND ".join(clauses) if where else "WHERE " + " AND ".join(clauses)
        params.append(limit)
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    s.session_id, s.source, s.html_path, s.cwd, s.started_at,
                    s.ended_at, s.summary, m.role, m.timestamp, m.ordinal,
                    m.text, substr(m.text, 1, 220) AS snippet
                FROM messages m
                JOIN sessions s ON s.session_id = m.session_id
                {where}
                ORDER BY m.timestamp DESC, m.ordinal DESC
                LIMIT ?
                """.format(where=where),
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def _time_clause(
        self,
        start: Optional[str],
        end: Optional[str],
        prefix: str,
    ):
        clauses = []
        params: List[Any] = []
        if start:
            clauses.append("{}.timestamp >= ?".format(prefix))
            params.append(start)
        if end:
            clauses.append("{}.timestamp <= ?".format(prefix))
            params.append(end)
        return ("AND " + " AND ".join(clauses) if clauses else ""), params

    def _insert_work_item(
        self,
        conn: sqlite3.Connection,
        session_id: str,
        item: WorkItemRecord,
    ) -> None:
        conn.execute(
            """
            INSERT INTO work_items (
                session_id, project, topic, status, summary, implemented,
                pending, files, evidence_message_ordinals
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                item.project,
                item.topic,
                item.status,
                item.summary,
                json.dumps(item.implemented, ensure_ascii=False),
                json.dumps(item.pending, ensure_ascii=False),
                json.dumps(item.files, ensure_ascii=False),
                json.dumps(item.evidence_message_ordinals, ensure_ascii=False),
            ),
        )

    def _decode_work_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        for key in ("implemented", "pending", "files", "evidence_message_ordinals"):
            item[key] = json.loads(item.get(key) or "[]")
        return item


def _query_terms(query: str) -> List[str]:
    return [
        term.lower()
        for term in re.findall(r"[0-9A-Za-z가-힣_-]+", query or "")
        if len(term.strip()) > 1
    ]
