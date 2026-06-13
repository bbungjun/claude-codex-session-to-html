# Local Dev Memory MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local development memory system that indexes Claude Code and Codex CLI sessions, supports time/topic/progress search, and exposes the results through a CLI and MCP server with links back to generated HTML logs.

**Architecture:** Keep the current HTML generation flow as the human-readable archive. Add a SQLite index beside the HTML files, populate it from the same Claude/Codex JSONL sessions, add a lightweight CLI for debugging and daily use, then wrap the same search service with a Python MCP server. Work-item extraction starts with deterministic heuristics and can later be upgraded to LLM-assisted summaries.

**Tech Stack:** Python 3.8+ standard library, SQLite FTS5, `unittest`, existing Bash watcher, optional `mcp` Python package for the MCP server, existing HTML converter scripts.

---

## Product Shape

The finished system should answer questions like:

```text
어제 agent chat 봇을 구현할 때 pipeline 구조를 어디까지 구현했지?
```

Expected answer shape:

```text
어제 agent chat bot / pipeline 관련 세션 2개를 찾았습니다.

구현된 부분:
- pipeline skeleton
- message normalization
- agent routing
- tool dispatch interface

남은 부분:
- persistence
- retry policy
- streaming status events

관련 HTML:
- C:\Users\...\session_history\rollout-....html
```

The system should not depend on scraping rendered HTML for search. HTML remains the visual archive. Search and progress recall use a structured SQLite index.

## File Structure

Create this package:

```text
session_memory/
  __init__.py
  models.py
  time_utils.py
  store.py
  indexer.py
  cli.py
  mcp_server.py
  parsers/
    __init__.py
    claude.py
    codex.py
  extractors/
    __init__.py
    work_items.py
```

Responsibilities:

- `session_memory/models.py`: dataclasses shared by parsers, indexer, store, CLI, and MCP server.
- `session_memory/time_utils.py`: Korean/English time-range helpers such as yesterday, today, and hour windows.
- `session_memory/store.py`: SQLite schema creation, upserts, FTS writes, and search queries.
- `session_memory/parsers/claude.py`: parse Claude Code JSONL into canonical records.
- `session_memory/parsers/codex.py`: parse Codex CLI JSONL into canonical records.
- `session_memory/extractors/work_items.py`: deterministic extraction of project/topic/progress signals from messages.
- `session_memory/indexer.py`: index one JSONL session and connect it to generated HTML.
- `session_memory/cli.py`: local command line search/open/debug interface.
- `session_memory/mcp_server.py`: MCP tools and resources backed by the same store.

Modify these existing files:

- `hooks/session_to_html.py`: after HTML write, call indexer for Claude sessions.
- `hooks/codex_to_html.py`: after HTML write, call indexer for Codex sessions.
- `install.sh`: copy `session_memory/` into `~/.claude/hooks/session_memory`, install optional MCP entrypoint docs, preserve current output prompt.
- `README.md`: document index, CLI, and MCP usage in English.
- `README.ko.md`: document index, CLI, and MCP usage in Korean.
- `tests/test_default_output_paths.py`: keep existing path/watch tests and add watcher/index integration tests where appropriate.

Create these tests:

```text
tests/fixtures/claude_stack.jsonl
tests/fixtures/codex_pipeline.jsonl
tests/test_parsers.py
tests/test_store.py
tests/test_indexer.py
tests/test_time_utils.py
tests/test_cli.py
tests/test_mcp_server.py
```

## SQLite Schema

Use a single SQLite file named `index.sqlite` in the selected output directory:

```sql
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
```

Use delete-and-reinsert semantics for `messages`, `messages_fts`, and `work_items` when re-indexing one session. This keeps the implementation simple and idempotent.

## Task 1: Add Shared Models

**Files:**
- Create: `session_memory/__init__.py`
- Create: `session_memory/models.py`
- Test: `tests/test_parsers.py`

- [ ] **Step 1: Write the failing model shape test**

Add to `tests/test_parsers.py`:

```python
import unittest
from session_memory.models import MessageRecord, SessionRecord


class ModelTests(unittest.TestCase):
    def test_session_record_holds_canonical_fields(self):
        message = MessageRecord(
            role="user",
            timestamp="2026-06-12T15:00:00+09:00",
            text="agent chat bot pipeline",
            ordinal=0,
        )
        record = SessionRecord(
            session_id="abc",
            source="codex",
            jsonl_path="/tmp/session.jsonl",
            html_path="/tmp/session.html",
            cwd="/tmp/project",
            started_at="2026-06-12T15:00:00+09:00",
            ended_at="2026-06-12T15:01:00+09:00",
            messages=[message],
            summary="agent chat bot pipeline",
        )

        self.assertEqual(record.session_id, "abc")
        self.assertEqual(record.source, "codex")
        self.assertEqual(record.messages[0].text, "agent chat bot pipeline")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python -B -m unittest tests.test_parsers
```

Expected: `ModuleNotFoundError: No module named 'session_memory'`.

- [ ] **Step 3: Add minimal model implementation**

Create `session_memory/__init__.py`:

```python
"""Local session memory indexing for Claude Code and Codex CLI."""
```

Create `session_memory/models.py`:

```python
from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class MessageRecord:
    role: str
    timestamp: str
    text: str
    ordinal: int


@dataclass(frozen=True)
class WorkItemRecord:
    project: str
    topic: str
    status: str
    summary: str
    implemented: List[str] = field(default_factory=list)
    pending: List[str] = field(default_factory=list)
    files: List[str] = field(default_factory=list)
    evidence_message_ordinals: List[int] = field(default_factory=list)


@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    source: str
    jsonl_path: str
    html_path: str
    cwd: str
    started_at: str
    ended_at: str
    messages: List[MessageRecord]
    summary: str = ""
    work_items: List[WorkItemRecord] = field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
python -B -m unittest tests.test_parsers
```

Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add session_memory/__init__.py session_memory/models.py tests/test_parsers.py
git commit -m "Add session memory models"
```

## Task 2: Add Time Range Utilities

**Files:**
- Create: `session_memory/time_utils.py`
- Test: `tests/test_time_utils.py`

- [ ] **Step 1: Write failing tests for Korean time phrases**

Create `tests/test_time_utils.py`:

```python
import unittest
from datetime import datetime, timezone, timedelta
from session_memory.time_utils import resolve_time_range


KST = timezone(timedelta(hours=9))


class TimeUtilsTests(unittest.TestCase):
    def test_resolves_yesterday_three_oclock(self):
        now = datetime(2026, 6, 13, 10, 0, tzinfo=KST)

        start, end = resolve_time_range("어제 3시", now=now)

        self.assertEqual(start.isoformat(), "2026-06-12T15:00:00+09:00")
        self.assertEqual(end.isoformat(), "2026-06-12T15:59:59+09:00")

    def test_resolves_yesterday_without_hour_to_full_day(self):
        now = datetime(2026, 6, 13, 10, 0, tzinfo=KST)

        start, end = resolve_time_range("어제", now=now)

        self.assertEqual(start.isoformat(), "2026-06-12T00:00:00+09:00")
        self.assertEqual(end.isoformat(), "2026-06-12T23:59:59+09:00")

    def test_empty_query_defaults_to_wide_range(self):
        now = datetime(2026, 6, 13, 10, 0, tzinfo=KST)

        start, end = resolve_time_range("", now=now)

        self.assertEqual(start.isoformat(), "1970-01-01T00:00:00+09:00")
        self.assertEqual(end.isoformat(), "2026-06-13T10:00:00+09:00")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python -B -m unittest tests.test_time_utils
```

Expected: `ModuleNotFoundError` or `ImportError` for `session_memory.time_utils`.

- [ ] **Step 3: Implement deterministic time parsing**

Create `session_memory/time_utils.py`:

```python
import re
from datetime import datetime, time, timezone, timedelta
from typing import Tuple


KST = timezone(timedelta(hours=9))


def _coerce_kst(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=KST)
    return dt.astimezone(KST)


def resolve_time_range(query: str, now: datetime | None = None) -> Tuple[datetime, datetime]:
    current = _coerce_kst(now or datetime.now(KST))
    text = query.strip().lower()
    if not text:
        return datetime(1970, 1, 1, tzinfo=KST), current

    base_date = current.date()
    if "어제" in text or "yesterday" in text:
        base_date = (current - timedelta(days=1)).date()
    elif "오늘" in text or "today" in text:
        base_date = current.date()

    hour = _extract_hour(text)
    if hour is None:
        return (
            datetime.combine(base_date, time(0, 0, 0), tzinfo=KST),
            datetime.combine(base_date, time(23, 59, 59), tzinfo=KST),
        )

    return (
        datetime.combine(base_date, time(hour, 0, 0), tzinfo=KST),
        datetime.combine(base_date, time(hour, 59, 59), tzinfo=KST),
    )


def _extract_hour(text: str) -> int | None:
    korean_match = re.search(r"(\d{1,2})\s*시", text)
    if korean_match:
        hour = int(korean_match.group(1))
        return hour if 0 <= hour <= 23 else None

    english_match = re.search(r"\b(\d{1,2})(?::\d{2})?\s*(am|pm)?\b", text)
    if not english_match:
        return None

    hour = int(english_match.group(1))
    suffix = english_match.group(2)
    if suffix == "pm" and hour < 12:
        hour += 12
    if suffix == "am" and hour == 12:
        hour = 0
    return hour if 0 <= hour <= 23 else None
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
python -B -m unittest tests.test_time_utils
```

Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add session_memory/time_utils.py tests/test_time_utils.py
git commit -m "Add session memory time parsing"
```

## Task 3: Add Claude and Codex Parsers

**Files:**
- Create: `session_memory/parsers/__init__.py`
- Create: `session_memory/parsers/claude.py`
- Create: `session_memory/parsers/codex.py`
- Create: `tests/fixtures/claude_stack.jsonl`
- Create: `tests/fixtures/codex_pipeline.jsonl`
- Modify: `tests/test_parsers.py`

- [ ] **Step 1: Add realistic fixture files**

Create `tests/fixtures/claude_stack.jsonl`:

```jsonl
{"type":"user","cwd":"/home/me/project","sessionId":"claude-1","timestamp":"2026-06-12T15:00:00.000Z","message":{"role":"user","content":"agent chat 봇 pipeline 구조 어디까지 구현했지?"}}
{"type":"assistant","cwd":"/home/me/project","sessionId":"claude-1","timestamp":"2026-06-12T15:01:00.000Z","message":{"role":"assistant","content":[{"type":"text","text":"pipeline skeleton과 message routing까지 구현했습니다. persistence는 아직 남았습니다."}]}}
```

Create `tests/fixtures/codex_pipeline.jsonl`:

```jsonl
{"type":"session_meta","timestamp":"2026-06-12T15:02:00.000Z","payload":{"cwd":"/home/me/agent-chat"}}
{"type":"event_msg","timestamp":"2026-06-12T15:03:00.000Z","payload":{"type":"user_message","message":"agent chat bot pipeline 구현 어디까지 됐어?"}}
{"type":"event_msg","timestamp":"2026-06-12T15:04:00.000Z","payload":{"type":"agent_message","message":"message normalization, agent routing, tool dispatch interface까지 구현했습니다. retry policy와 persistence는 남았습니다.","phase":"final"}}
```

- [ ] **Step 2: Write failing parser tests**

Append to `tests/test_parsers.py`:

```python
from pathlib import Path
from session_memory.parsers.claude import parse_claude_jsonl
from session_memory.parsers.codex import parse_codex_jsonl


class ParserTests(unittest.TestCase):
    def test_parse_claude_jsonl(self):
        fixture = Path("tests/fixtures/claude_stack.jsonl")

        record = parse_claude_jsonl(fixture, html_path="/tmp/claude.html")

        self.assertEqual(record.source, "claude")
        self.assertEqual(record.session_id, "claude-1")
        self.assertEqual(record.cwd, "/home/me/project")
        self.assertEqual(len(record.messages), 2)
        self.assertIn("pipeline 구조", record.messages[0].text)
        self.assertIn("persistence", record.messages[1].text)

    def test_parse_codex_jsonl(self):
        fixture = Path("tests/fixtures/codex_pipeline.jsonl")

        record = parse_codex_jsonl(fixture, html_path="/tmp/codex.html")

        self.assertEqual(record.source, "codex")
        self.assertEqual(record.cwd, "/home/me/agent-chat")
        self.assertEqual(len(record.messages), 2)
        self.assertIn("agent chat bot", record.messages[0].text)
        self.assertIn("tool dispatch", record.messages[1].text)
```

- [ ] **Step 3: Run parser tests to verify failure**

Run:

```bash
python -B -m unittest tests.test_parsers
```

Expected: `ModuleNotFoundError` for parser modules.

- [ ] **Step 4: Implement parser package**

Create `session_memory/parsers/__init__.py`:

```python
"""JSONL parsers for supported AI CLI session formats."""
```

Create `session_memory/parsers/claude.py`:

```python
import json
from pathlib import Path
from typing import Any, List
from session_memory.models import MessageRecord, SessionRecord


def parse_claude_jsonl(jsonl_path: Path, html_path: str) -> SessionRecord:
    messages: List[MessageRecord] = []
    session_id = jsonl_path.stem
    cwd = ""
    timestamps: List[str] = []

    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        if obj.get("type") not in ("user", "assistant"):
            continue

        timestamp = obj.get("timestamp", "")
        text = _extract_claude_text(obj.get("message", {}).get("content", ""))
        if not text.strip():
            continue

        session_id = obj.get("sessionId") or obj.get("session_id") or session_id
        cwd = obj.get("cwd", cwd)
        timestamps.append(timestamp)
        messages.append(
            MessageRecord(
                role=obj.get("type", ""),
                timestamp=timestamp,
                text=text.strip(),
                ordinal=len(messages),
            )
        )

    started_at = timestamps[0] if timestamps else ""
    ended_at = timestamps[-1] if timestamps else ""
    summary = _make_summary(messages)
    return SessionRecord(
        session_id=session_id,
        source="claude",
        jsonl_path=str(jsonl_path),
        html_path=html_path,
        cwd=cwd,
        started_at=started_at,
        ended_at=ended_at,
        messages=messages,
        summary=summary,
    )


def _extract_claude_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
        return "\n".join(part for part in parts if part)
    return str(content)


def _make_summary(messages: List[MessageRecord]) -> str:
    for message in messages:
        if message.role == "user" and message.text:
            return message.text[:160]
    return messages[0].text[:160] if messages else ""
```

Create `session_memory/parsers/codex.py`:

```python
import json
from pathlib import Path
from typing import List
from session_memory.models import MessageRecord, SessionRecord


def parse_codex_jsonl(jsonl_path: Path, html_path: str) -> SessionRecord:
    messages: List[MessageRecord] = []
    cwd = ""
    timestamps: List[str] = []

    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        event_type = obj.get("type", "")
        payload = obj.get("payload", {})
        timestamp = obj.get("timestamp", "")

        if event_type == "session_meta":
            cwd = payload.get("cwd", cwd)
            continue

        if event_type != "event_msg":
            continue

        payload_type = payload.get("type", "")
        if payload_type == "user_message":
            role = "user"
            text = payload.get("message", "")
        elif payload_type == "agent_message":
            role = "assistant"
            text = payload.get("message", "")
        else:
            continue

        if not str(text).strip():
            continue

        timestamps.append(timestamp)
        messages.append(
            MessageRecord(
                role=role,
                timestamp=timestamp,
                text=str(text).strip(),
                ordinal=len(messages),
            )
        )

    return SessionRecord(
        session_id=jsonl_path.stem,
        source="codex",
        jsonl_path=str(jsonl_path),
        html_path=html_path,
        cwd=cwd,
        started_at=timestamps[0] if timestamps else "",
        ended_at=timestamps[-1] if timestamps else "",
        messages=messages,
        summary=_make_summary(messages),
    )


def _make_summary(messages: List[MessageRecord]) -> str:
    for message in messages:
        if message.role == "user" and message.text:
            return message.text[:160]
    return messages[0].text[:160] if messages else ""
```

- [ ] **Step 5: Run parser tests to verify pass**

Run:

```bash
python -B -m unittest tests.test_parsers
```

Expected: `OK`.

- [ ] **Step 6: Commit**

```bash
git add session_memory/parsers tests/fixtures tests/test_parsers.py
git commit -m "Add Claude and Codex session parsers"
```

## Task 4: Add SQLite Store and FTS Search

**Files:**
- Create: `session_memory/store.py`
- Test: `tests/test_store.py`

- [ ] **Step 1: Write failing store tests**

Create `tests/test_store.py`:

```python
import tempfile
import unittest
from pathlib import Path
from session_memory.models import MessageRecord, SessionRecord, WorkItemRecord
from session_memory.store import SessionStore


class StoreTests(unittest.TestCase):
    def test_upsert_and_keyword_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "index.sqlite"
            store = SessionStore(db_path)
            record = SessionRecord(
                session_id="s1",
                source="codex",
                jsonl_path="/tmp/s1.jsonl",
                html_path="/tmp/s1.html",
                cwd="/tmp/agent-chat",
                started_at="2026-06-12T15:00:00+09:00",
                ended_at="2026-06-12T15:10:00+09:00",
                messages=[
                    MessageRecord("user", "2026-06-12T15:00:00+09:00", "agent chat pipeline", 0),
                    MessageRecord("assistant", "2026-06-12T15:01:00+09:00", "routing implemented, persistence pending", 1),
                ],
                summary="agent chat pipeline",
                work_items=[
                    WorkItemRecord(
                        project="agent chat",
                        topic="pipeline",
                        status="in_progress",
                        summary="routing implemented, persistence pending",
                        implemented=["routing"],
                        pending=["persistence"],
                        files=["src/pipeline.ts"],
                        evidence_message_ordinals=[1],
                    )
                ],
            )

            store.upsert_session(record)
            results = store.search_messages("pipeline", limit=5)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["session_id"], "s1")
            self.assertIn("pipeline", results[0]["snippet"])

    def test_time_range_filters_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "index.sqlite"
            store = SessionStore(db_path)
            store.upsert_session(
                SessionRecord(
                    session_id="s2",
                    source="claude",
                    jsonl_path="/tmp/s2.jsonl",
                    html_path="/tmp/s2.html",
                    cwd="/tmp/project",
                    started_at="2026-06-12T15:00:00+09:00",
                    ended_at="2026-06-12T15:05:00+09:00",
                    messages=[MessageRecord("user", "2026-06-12T15:00:00+09:00", "stack", 0)],
                )
            )

            results = store.find_sessions(
                start_time="2026-06-12T14:00:00+09:00",
                end_time="2026-06-12T16:00:00+09:00",
            )

            self.assertEqual([row["session_id"] for row in results], ["s2"])
```

- [ ] **Step 2: Run store tests to verify failure**

Run:

```bash
python -B -m unittest tests.test_store
```

Expected: `ModuleNotFoundError` for `session_memory.store`.

- [ ] **Step 3: Implement SQLite store**

Create `session_memory/store.py`:

```python
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from session_memory.models import SessionRecord


class SessionStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                PRAGMA foreign_keys = ON;
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
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                """
                INSERT INTO sessions (
                    session_id, source, jsonl_path, html_path, cwd,
                    started_at, ended_at, message_count, summary, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    source=excluded.source,
                    jsonl_path=excluded.jsonl_path,
                    html_path=excluded.html_path,
                    cwd=excluded.cwd,
                    started_at=excluded.started_at,
                    ended_at=excluded.ended_at,
                    message_count=excluded.message_count,
                    summary=excluded.summary,
                    updated_at=excluded.updated_at
                """,
                (
                    record.session_id,
                    record.source,
                    record.jsonl_path,
                    record.html_path,
                    record.cwd,
                    record.started_at,
                    record.ended_at,
                    len(record.messages),
                    record.summary,
                    now,
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
                    (record.session_id, record.source, message.role, message.timestamp, message.text, message.ordinal),
                )
                conn.execute(
                    "INSERT INTO messages_fts (session_id, role, text) VALUES (?, ?, ?)",
                    (record.session_id, message.role, message.text),
                )
            for item in record.work_items:
                conn.execute(
                    """
                    INSERT INTO work_items (
                        session_id, project, topic, status, summary,
                        implemented, pending, files, evidence_message_ordinals
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.session_id,
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

    def search_messages(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT f.session_id, s.source, s.html_path, s.summary, snippet(messages_fts, 2, '[', ']', ' ... ', 12) AS snippet
                FROM messages_fts f
                JOIN sessions s ON s.session_id = f.session_id
                WHERE messages_fts MATCH ?
                GROUP BY f.session_id
                ORDER BY s.ended_at DESC
                LIMIT ?
                """,
                (query, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def find_sessions(self, start_time: str, end_time: str, limit: int = 20) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM sessions
                WHERE ended_at >= ? AND started_at <= ?
                ORDER BY ended_at DESC
                LIMIT ?
                """,
                (start_time, end_time, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_session(self, session_id: str) -> Dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        return dict(row) if row else None
```

- [ ] **Step 4: Run store tests to verify pass**

Run:

```bash
python -B -m unittest tests.test_store
```

Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add session_memory/store.py tests/test_store.py
git commit -m "Add SQLite session store"
```

## Task 5: Add Work Item Heuristic Extraction

**Files:**
- Create: `session_memory/extractors/__init__.py`
- Create: `session_memory/extractors/work_items.py`
- Test: `tests/test_indexer.py`

- [ ] **Step 1: Write failing extraction tests**

Create `tests/test_indexer.py`:

```python
import unittest
from session_memory.extractors.work_items import extract_work_items
from session_memory.models import MessageRecord


class WorkItemExtractorTests(unittest.TestCase):
    def test_extracts_agent_pipeline_progress(self):
        messages = [
            MessageRecord("user", "2026-06-12T15:00:00+09:00", "agent chat bot pipeline 어디까지 구현했지?", 0),
            MessageRecord("assistant", "2026-06-12T15:01:00+09:00", "pipeline skeleton과 routing은 구현했고 persistence와 retry는 남았습니다.", 1),
        ]

        items = extract_work_items(messages, cwd="/home/me/agent-chat")

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].project, "agent-chat")
        self.assertEqual(items[0].topic, "pipeline")
        self.assertEqual(items[0].status, "in_progress")
        self.assertIn("routing", items[0].implemented)
        self.assertIn("persistence", items[0].pending)
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
python -B -m unittest tests.test_indexer
```

Expected: `ModuleNotFoundError` for `session_memory.extractors`.

- [ ] **Step 3: Implement simple deterministic extractor**

Create `session_memory/extractors/__init__.py`:

```python
"""Progress and task extraction helpers."""
```

Create `session_memory/extractors/work_items.py`:

```python
import re
from pathlib import Path
from typing import List
from session_memory.models import MessageRecord, WorkItemRecord


IMPLEMENTED_HINTS = ("구현", "완료", "implemented", "built", "added", "created")
PENDING_HINTS = ("남", "아직", "pending", "remain", "left", "not implemented")
TOPIC_WORDS = ("pipeline", "router", "routing", "agent", "mcp", "index", "sqlite", "watcher")


def extract_work_items(messages: List[MessageRecord], cwd: str) -> List[WorkItemRecord]:
    combined = "\n".join(message.text for message in messages)
    topic = _extract_topic(combined)
    if not topic:
        return []

    implemented = _extract_implemented(combined)
    pending = _extract_pending(combined)
    status = "in_progress" if pending else "implemented" if implemented else "mentioned"
    summary = _make_summary(topic, implemented, pending)

    return [
        WorkItemRecord(
            project=_project_from_cwd(cwd),
            topic=topic,
            status=status,
            summary=summary,
            implemented=implemented,
            pending=pending,
            files=_extract_files(combined),
            evidence_message_ordinals=[message.ordinal for message in messages if topic in message.text.lower()],
        )
    ]


def _extract_topic(text: str) -> str:
    lowered = text.lower()
    for word in TOPIC_WORDS:
        if word in lowered:
            return "pipeline" if word in ("pipeline", "router", "routing") else word
    return ""


def _extract_implemented(text: str) -> List[str]:
    lowered = text.lower()
    results = []
    for candidate in ("pipeline skeleton", "message normalization", "routing", "tool dispatch", "index", "watcher"):
        if candidate in lowered and any(hint in lowered for hint in IMPLEMENTED_HINTS):
            results.append(candidate)
    return _dedupe(results)


def _extract_pending(text: str) -> List[str]:
    lowered = text.lower()
    results = []
    for candidate in ("persistence", "retry", "streaming", "tests", "mcp server"):
        if candidate in lowered and any(hint in lowered for hint in PENDING_HINTS):
            results.append(candidate)
    return _dedupe(results)


def _extract_files(text: str) -> List[str]:
    matches = re.findall(r"[\w./-]+\.(?:py|ts|tsx|js|jsx|md|json|sh)", text)
    return _dedupe(matches)


def _project_from_cwd(cwd: str) -> str:
    if not cwd:
        return ""
    return Path(cwd).name


def _make_summary(topic: str, implemented: List[str], pending: List[str]) -> str:
    parts = [f"topic={topic}"]
    if implemented:
        parts.append("implemented: " + ", ".join(implemented))
    if pending:
        parts.append("pending: " + ", ".join(pending))
    return "; ".join(parts)


def _dedupe(values: List[str]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
```

- [ ] **Step 4: Run test to verify pass**

Run:

```bash
python -B -m unittest tests.test_indexer
```

Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add session_memory/extractors tests/test_indexer.py
git commit -m "Extract work item progress from sessions"
```

## Task 6: Add Indexer Service

**Files:**
- Create: `session_memory/indexer.py`
- Modify: `tests/test_indexer.py`

- [ ] **Step 1: Add failing indexer test**

Append to `tests/test_indexer.py`:

```python
import tempfile
from pathlib import Path
from session_memory.indexer import index_session
from session_memory.store import SessionStore


class IndexerTests(unittest.TestCase):
    def test_indexes_codex_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "index.sqlite"
            fixture = Path("tests/fixtures/codex_pipeline.jsonl")
            html_path = Path(tmp) / "codex.html"
            html_path.write_text("<html>session</html>", encoding="utf-8")

            record = index_session("codex", fixture, html_path, db_path)

            self.assertEqual(record.source, "codex")
            store = SessionStore(db_path)
            results = store.search_messages("pipeline", limit=5)
            self.assertEqual(results[0]["session_id"], fixture.stem)
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
python -B -m unittest tests.test_indexer
```

Expected: `ModuleNotFoundError` for `session_memory.indexer`.

- [ ] **Step 3: Implement indexer**

Create `session_memory/indexer.py`:

```python
from pathlib import Path
from session_memory.extractors.work_items import extract_work_items
from session_memory.parsers.claude import parse_claude_jsonl
from session_memory.parsers.codex import parse_codex_jsonl
from session_memory.store import SessionStore


def index_session(source: str, jsonl_path: Path | str, html_path: Path | str, db_path: Path | str):
    jsonl = Path(jsonl_path)
    html = Path(html_path)
    db = Path(db_path)

    if source == "claude":
        record = parse_claude_jsonl(jsonl, html_path=str(html))
    elif source == "codex":
        record = parse_codex_jsonl(jsonl, html_path=str(html))
    else:
        raise ValueError(f"unsupported session source: {source}")

    record = _with_work_items(record)
    SessionStore(db).upsert_session(record)
    return record


def _with_work_items(record):
    from session_memory.models import SessionRecord

    work_items = extract_work_items(record.messages, cwd=record.cwd)
    return SessionRecord(
        session_id=record.session_id,
        source=record.source,
        jsonl_path=record.jsonl_path,
        html_path=record.html_path,
        cwd=record.cwd,
        started_at=record.started_at,
        ended_at=record.ended_at,
        messages=record.messages,
        summary=record.summary,
        work_items=work_items,
    )
```

- [ ] **Step 4: Run indexer tests**

Run:

```bash
python -B -m unittest tests.test_indexer
```

Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add session_memory/indexer.py tests/test_indexer.py
git commit -m "Add session indexer service"
```

## Task 7: Integrate Indexer Into HTML Converters

**Files:**
- Modify: `hooks/session_to_html.py`
- Modify: `hooks/codex_to_html.py`
- Test: `tests/test_default_output_paths.py`

- [ ] **Step 1: Add failing converter integration assertions**

Append to `tests/test_default_output_paths.py`:

```python
    def test_converters_update_sqlite_index_after_html_write(self):
        claude_converter = (ROOT / "hooks" / "session_to_html.py").read_text(encoding="utf-8")
        codex_converter = (ROOT / "hooks" / "codex_to_html.py").read_text(encoding="utf-8")

        self.assertIn("from session_memory.indexer import index_session", claude_converter)
        self.assertIn("index_session(\"claude\", target_file, out_file, OUTPUT_DIR / \"index.sqlite\")", claude_converter)
        self.assertIn("from session_memory.indexer import index_session", codex_converter)
        self.assertIn("index_session(\"codex\", target_file, out_file, OUTPUT_DIR / \"index.sqlite\")", codex_converter)
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
python -B -m unittest tests.test_default_output_paths
```

Expected: assertion failure because converters do not import or call `index_session`.

- [ ] **Step 3: Add guarded index updates to converters**

In `hooks/session_to_html.py`, add near imports:

```python
try:
    from session_memory.indexer import index_session
except ImportError:
    index_session = None
```

After `out_file.write_text(html, encoding="utf-8")`, add:

```python
    if index_session:
        index_session("claude", target_file, out_file, OUTPUT_DIR / "index.sqlite")
```

In `hooks/codex_to_html.py`, add the same import guard:

```python
try:
    from session_memory.indexer import index_session
except ImportError:
    index_session = None
```

After `out_file.write_text(html, encoding="utf-8")`, add:

```python
    if index_session:
        index_session("codex", target_file, out_file, OUTPUT_DIR / "index.sqlite")
```

- [ ] **Step 4: Run converter integration tests**

Run:

```bash
python -B -m unittest tests.test_default_output_paths
```

Expected: `OK`.

- [ ] **Step 5: Run all tests**

Run:

```bash
python -B -m unittest discover
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add hooks/session_to_html.py hooks/codex_to_html.py tests/test_default_output_paths.py
git commit -m "Update HTML converters to index sessions"
```

## Task 8: Install Package Files With Hooks

**Files:**
- Modify: `install.sh`
- Test: `tests/test_default_output_paths.py`

- [ ] **Step 1: Add failing installer assertions**

Append to `tests/test_default_output_paths.py`:

```python
    def test_installer_copies_session_memory_package(self):
        install_script = (ROOT / "install.sh").read_text(encoding="utf-8")

        self.assertIn('cp -R "$PACKAGE_DIR" "$HOOKS_DIR/session_memory"', install_script)
        self.assertIn('rm -rf "$HOOKS_DIR/session_memory"', install_script)
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
python -B -m unittest tests.test_default_output_paths
```

Expected: assertion failure because installer does not copy `session_memory`.

- [ ] **Step 3: Modify installer**

In `install.sh`, after `SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)/hooks"`, add:

```bash
PACKAGE_DIR="$(cd "$(dirname "$0")" && pwd)/session_memory"
```

Before converter copy blocks, add:

```bash
rm -rf "$HOOKS_DIR/session_memory"
cp -R "$PACKAGE_DIR" "$HOOKS_DIR/session_memory"
```

This makes installed converters able to import `session_memory.indexer`.

- [ ] **Step 4: Run installer tests and shell syntax check**

Run:

```bash
python -B -m unittest tests.test_default_output_paths
bash -n install.sh
```

Expected: `OK` for tests and no output from `bash -n`.

- [ ] **Step 5: Commit**

```bash
git add install.sh tests/test_default_output_paths.py
git commit -m "Install session memory package with hooks"
```

## Task 9: Add CLI Search

**Files:**
- Create: `session_memory/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_cli.py`:

```python
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from session_memory.cli import main
from session_memory.models import MessageRecord, SessionRecord
from session_memory.store import SessionStore


class CliTests(unittest.TestCase):
    def test_search_outputs_html_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "index.sqlite"
            store = SessionStore(db_path)
            store.upsert_session(
                SessionRecord(
                    session_id="s1",
                    source="codex",
                    jsonl_path="/tmp/s1.jsonl",
                    html_path="C:/history/s1.html",
                    cwd="/tmp/agent-chat",
                    started_at="2026-06-12T15:00:00+09:00",
                    ended_at="2026-06-12T15:10:00+09:00",
                    messages=[MessageRecord("user", "2026-06-12T15:00:00+09:00", "agent pipeline", 0)],
                    summary="agent pipeline",
                )
            )
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                exit_code = main(["search", "pipeline", "--db", str(db_path)])

            self.assertEqual(exit_code, 0)
            self.assertIn("s1", stdout.getvalue())
            self.assertIn("C:/history/s1.html", stdout.getvalue())
```

- [ ] **Step 2: Run CLI test to verify failure**

Run:

```bash
python -B -m unittest tests.test_cli
```

Expected: `ModuleNotFoundError` for `session_memory.cli`.

- [ ] **Step 3: Implement CLI**

Create `session_memory/cli.py`:

```python
import argparse
import sys
from pathlib import Path
from session_memory.store import SessionStore


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="session-memory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("search")
    search_parser.add_argument("query")
    search_parser.add_argument("--db", required=True)
    search_parser.add_argument("--limit", type=int, default=10)

    args = parser.parse_args(argv)
    if args.command == "search":
        return _search(args)
    return 1


def _search(args) -> int:
    store = SessionStore(Path(args.db))
    rows = store.search_messages(args.query, limit=args.limit)
    for row in rows:
        print(f"{row['session_id']} | {row['source']} | {row['html_path']}")
        print(f"  {row['snippet']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run CLI tests**

Run:

```bash
python -B -m unittest tests.test_cli
```

Expected: `OK`.

- [ ] **Step 5: Manual CLI smoke test**

Run after indexing a fixture through `index_session`:

```bash
python -m session_memory.cli search pipeline --db C:/Users/PC/Desktop/session_history/index.sqlite
```

Expected: at least one line containing a session id and `.html` path if the local index has pipeline-related sessions.

- [ ] **Step 6: Commit**

```bash
git add session_memory/cli.py tests/test_cli.py
git commit -m "Add session memory search CLI"
```

## Task 10: Add MCP Server

**Files:**
- Create: `session_memory/mcp_server.py`
- Create: `tests/test_mcp_server.py`
- Modify: `README.md`
- Modify: `README.ko.md`

- [ ] **Step 1: Add dependency note**

This project currently uses only Bash and Python standard library. MCP support needs an optional dependency:

```bash
pip install mcp
```

Keep the core HTML/index/CLI functionality working without `mcp` installed.

- [ ] **Step 2: Write failing MCP helper tests**

Create `tests/test_mcp_server.py`:

```python
import tempfile
import unittest
from pathlib import Path
from session_memory.mcp_server import build_search_payload
from session_memory.models import MessageRecord, SessionRecord
from session_memory.store import SessionStore


class McpServerTests(unittest.TestCase):
    def test_build_search_payload_contains_html_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "index.sqlite"
            store = SessionStore(db_path)
            store.upsert_session(
                SessionRecord(
                    session_id="s1",
                    source="codex",
                    jsonl_path="/tmp/s1.jsonl",
                    html_path="C:/history/s1.html",
                    cwd="/tmp/agent-chat",
                    started_at="2026-06-12T15:00:00+09:00",
                    ended_at="2026-06-12T15:10:00+09:00",
                    messages=[MessageRecord("user", "2026-06-12T15:00:00+09:00", "agent pipeline", 0)],
                    summary="agent pipeline",
                )
            )

            payload = build_search_payload(db_path, query="pipeline", limit=5)

            self.assertEqual(payload[0]["session_id"], "s1")
            self.assertEqual(payload[0]["html_path"], "C:/history/s1.html")
```

- [ ] **Step 3: Run MCP tests to verify failure**

Run:

```bash
python -B -m unittest tests.test_mcp_server
```

Expected: `ModuleNotFoundError` for `session_memory.mcp_server`.

- [ ] **Step 4: Implement MCP server with import guard**

Create `session_memory/mcp_server.py`:

```python
import os
from pathlib import Path
from typing import Any, Dict, List
from session_memory.store import SessionStore


def build_search_payload(db_path: Path | str, query: str, limit: int = 10) -> List[Dict[str, Any]]:
    store = SessionStore(Path(db_path))
    return store.search_messages(query, limit=limit)


def build_session_payload(db_path: Path | str, session_id: str) -> Dict[str, Any] | None:
    return SessionStore(Path(db_path)).get_session(session_id)


def create_server():
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError("MCP support requires: pip install mcp") from exc

    db_path = Path(os.environ.get("SESSION_MEMORY_DB", "index.sqlite"))
    mcp = FastMCP("local-dev-memory")

    @mcp.tool()
    def search_sessions(query: str, limit: int = 10):
        """Search local Claude/Codex session history and return HTML paths."""
        return build_search_payload(db_path, query=query, limit=limit)

    @mcp.tool()
    def get_session(session_id: str):
        """Return one indexed session by id."""
        return build_session_payload(db_path, session_id=session_id)

    @mcp.resource("session://{session_id}")
    def session_resource(session_id: str):
        session = build_session_payload(db_path, session_id=session_id)
        return session or {"error": f"session not found: {session_id}"}

    return mcp


def main() -> None:
    create_server().run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run MCP helper tests**

Run:

```bash
python -B -m unittest tests.test_mcp_server
```

Expected: `OK`.

- [ ] **Step 6: Document MCP usage**

Add to `README.md`:

```markdown
## MCP Server

Install the optional MCP dependency:

```bash
pip install mcp
```

Run the local MCP server with the SQLite index created in your output folder:

```bash
SESSION_MEMORY_DB=/mnt/c/Users/<you>/Desktop/session_history/index.sqlite python3 -m session_memory.mcp_server
```

Example questions:

```text
What did I discuss yesterday at 3 PM?
How far did I get on the agent chat bot pipeline?
Open the related session HTML.
```
```

Add equivalent Korean instructions to `README.ko.md`:

```markdown
## MCP 서버

선택 의존성을 설치합니다.

```bash
pip install mcp
```

저장 폴더의 SQLite index를 지정해서 MCP 서버를 실행합니다.

```bash
SESSION_MEMORY_DB=/mnt/c/Users/<you>/Desktop/session_history/index.sqlite python3 -m session_memory.mcp_server
```

예시 질문:

```text
어제 3시에 어떤 대화를 했었지?
agent chat bot pipeline 구조를 어디까지 구현했지?
관련 HTML 세션을 열어줘.
```
```

- [ ] **Step 7: Commit**

```bash
git add session_memory/mcp_server.py tests/test_mcp_server.py README.md README.ko.md
git commit -m "Add MCP server for session memory"
```

## Task 11: Add Progress Query Helpers

**Files:**
- Modify: `session_memory/store.py`
- Modify: `session_memory/mcp_server.py`
- Test: `tests/test_store.py`
- Test: `tests/test_mcp_server.py`

- [ ] **Step 1: Add failing work item query test**

Append to `tests/test_store.py`:

```python
    def test_find_work_items_by_project_and_topic(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "index.sqlite"
            store = SessionStore(db_path)
            store.upsert_session(
                SessionRecord(
                    session_id="s3",
                    source="codex",
                    jsonl_path="/tmp/s3.jsonl",
                    html_path="/tmp/s3.html",
                    cwd="/tmp/agent-chat",
                    started_at="2026-06-12T15:00:00+09:00",
                    ended_at="2026-06-12T15:05:00+09:00",
                    messages=[MessageRecord("assistant", "2026-06-12T15:00:00+09:00", "routing implemented", 0)],
                    work_items=[
                        WorkItemRecord(
                            project="agent-chat",
                            topic="pipeline",
                            status="in_progress",
                            summary="routing implemented, persistence pending",
                            implemented=["routing"],
                            pending=["persistence"],
                        )
                    ],
                )
            )

            rows = store.find_work_items(project="agent-chat", topic="pipeline")

            self.assertEqual(rows[0]["session_id"], "s3")
            self.assertIn("routing", rows[0]["implemented"])
```

- [ ] **Step 2: Run store test to verify failure**

Run:

```bash
python -B -m unittest tests.test_store
```

Expected: `AttributeError: 'SessionStore' object has no attribute 'find_work_items'`.

- [ ] **Step 3: Add store method**

Append to `SessionStore` in `session_memory/store.py`:

```python
    def find_work_items(self, project: str = "", topic: str = "", limit: int = 10) -> List[Dict[str, Any]]:
        clauses = []
        params: List[Any] = []
        if project:
            clauses.append("project LIKE ?")
            params.append(f"%{project}%")
        if topic:
            clauses.append("topic LIKE ?")
            params.append(f"%{topic}%")
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT w.*, s.html_path, s.started_at, s.ended_at, s.source
                FROM work_items w
                JOIN sessions s ON s.session_id = w.session_id
                {where}
                ORDER BY s.ended_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["implemented"] = json.loads(item["implemented"])
            item["pending"] = json.loads(item["pending"])
            item["files"] = json.loads(item["files"])
            item["evidence_message_ordinals"] = json.loads(item["evidence_message_ordinals"])
            result.append(item)
        return result
```

- [ ] **Step 4: Add MCP progress helper**

Append to `session_memory/mcp_server.py`:

```python
def build_progress_payload(db_path: Path | str, project: str = "", topic: str = "", limit: int = 10):
    return SessionStore(Path(db_path)).find_work_items(project=project, topic=topic, limit=limit)
```

Inside `create_server()`, add:

```python
    @mcp.tool()
    def get_project_progress(project: str = "", topic: str = "", limit: int = 10):
        """Return implementation progress extracted from local development sessions."""
        return build_progress_payload(db_path, project=project, topic=topic, limit=limit)
```

- [ ] **Step 5: Run relevant tests**

Run:

```bash
python -B -m unittest tests.test_store tests.test_mcp_server
```

Expected: `OK`.

- [ ] **Step 6: Commit**

```bash
git add session_memory/store.py session_memory/mcp_server.py tests/test_store.py tests/test_mcp_server.py
git commit -m "Add project progress lookup"
```

## Task 12: Full Verification and Documentation Polish

**Files:**
- Modify: `README.md`
- Modify: `README.ko.md`
- Optional modify: `tests/test_default_output_paths.py`

- [ ] **Step 1: Run all tests**

Run:

```bash
python -B -m unittest discover
```

Expected: every test module reports `OK`.

- [ ] **Step 2: Run shell syntax checks**

Run:

```bash
bash -n install.sh
bash -n hooks/session_watcher.sh
```

Expected: no output and exit code `0`.

- [ ] **Step 3: Run converter compile checks**

Run:

```bash
python -B -c "from pathlib import Path; files=('hooks/session_to_html.py','hooks/codex_to_html.py','session_memory/cli.py','session_memory/indexer.py','session_memory/store.py'); [compile(Path(p).read_text(encoding='utf-8'), p, 'exec') for p in files]"
```

Expected: no output and exit code `0`.

- [ ] **Step 4: Manual end-to-end smoke test**

Run from WSL after installing:

```bash
echo '{}' | python3 ~/.claude/hooks/codex_to_html.py
ls -l /mnt/c/Users/PC/Desktop/session_history/index.sqlite
python3 -m session_memory.cli search pipeline --db /mnt/c/Users/PC/Desktop/session_history/index.sqlite
```

Expected:

```text
index.sqlite exists
search command prints zero or more session rows without crashing
```

- [ ] **Step 5: README final check**

Confirm both docs include:

```text
HTML archive remains the primary visual output.
SQLite index enables local search.
CLI search is available without MCP.
MCP server requires optional pip install mcp.
Generated logs and indexes may contain sensitive data.
```

- [ ] **Step 6: Commit documentation polish**

```bash
git add README.md README.ko.md tests/test_default_output_paths.py
git commit -m "Document session memory search"
```

## Task 13: Release Checklist

**Files:**
- No code changes required if all previous tasks are complete.

- [ ] **Step 1: Verify git status**

Run:

```bash
git status --short
```

Expected: no output.

- [ ] **Step 2: Verify latest commits**

Run:

```bash
git log --oneline -8
```

Expected: recent commits include:

```text
Document session memory search
Add project progress lookup
Add MCP server for session memory
Add session memory search CLI
Update HTML converters to index sessions
```

- [ ] **Step 3: Push**

Run:

```bash
git push origin main
```

Expected: remote `main` updates successfully.

## Risk Notes

- Claude and Codex JSONL schemas may change. Parser tests with fixtures protect the current expected fields.
- Korean text can display incorrectly if files are read with the wrong encoding. All Python reads and writes must use `encoding="utf-8"`.
- MCP should remain optional. A user who only wants HTML export should not need to install the MCP package.
- Work-item extraction starts heuristic-based. It should answer common development-progress questions, but it should expose evidence HTML paths so users can verify.
- Index files may contain sensitive prompts, code, local paths, and command output. Treat `index.sqlite` with the same security warning as generated HTML.

## Self-Review

- Spec coverage: The plan covers SQLite indexing, CLI search, MCP tools/resources, progress extraction, converter integration, installer changes, docs, and verification.
- Placeholder scan: The plan contains concrete file paths, commands, expected outputs, and code snippets for each implementation task.
- Type consistency: The plan consistently uses `SessionRecord`, `MessageRecord`, `WorkItemRecord`, `SessionStore`, `index_session`, `build_search_payload`, and `build_progress_payload`.

