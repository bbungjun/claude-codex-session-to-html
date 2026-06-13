from pathlib import Path
import tempfile
import unittest

from session_memory.models import MessageRecord, SessionRecord, WorkItemRecord
from session_memory.store import SessionStore


class StoreTests(unittest.TestCase):
    def test_upsert_and_search_messages_returns_html_path(self):
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
                    messages=[
                        MessageRecord(
                            "user",
                            "2026-06-12T15:00:00+09:00",
                            "agent pipeline",
                            0,
                        )
                    ],
                    summary="agent pipeline",
                )
            )

            rows = store.search_messages("pipeline")

            self.assertEqual(rows[0]["session_id"], "s1")
            self.assertEqual(rows[0]["html_path"], "C:/history/s1.html")

    def test_reindexing_session_replaces_messages(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "index.sqlite"
            store = SessionStore(db_path)
            base = SessionRecord(
                session_id="s2",
                source="claude",
                jsonl_path="/tmp/s2.jsonl",
                html_path="/tmp/s2.html",
                cwd="/tmp/app",
                started_at="2026-06-12T15:00:00+09:00",
                ended_at="2026-06-12T15:00:00+09:00",
                messages=[MessageRecord("user", "2026-06-12T15:00:00+09:00", "old topic", 0)],
            )
            store.upsert_session(base)
            store.upsert_session(
                SessionRecord(
                    session_id="s2",
                    source="claude",
                    jsonl_path="/tmp/s2.jsonl",
                    html_path="/tmp/s2.html",
                    cwd="/tmp/app",
                    started_at="2026-06-12T15:00:00+09:00",
                    ended_at="2026-06-12T15:01:00+09:00",
                    messages=[MessageRecord("user", "2026-06-12T15:01:00+09:00", "new pipeline", 0)],
                )
            )

            self.assertEqual(store.search_messages("old"), [])
            self.assertEqual(store.search_messages("new")[0]["session_id"], "s2")

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
                    messages=[
                        MessageRecord(
                            "assistant",
                            "2026-06-12T15:00:00+09:00",
                            "routing implemented",
                            0,
                        )
                    ],
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


if __name__ == "__main__":
    unittest.main()

