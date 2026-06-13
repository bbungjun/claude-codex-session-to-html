from pathlib import Path
import tempfile
import unittest

from session_memory.mcp_server import build_progress_payload, build_search_payload
from session_memory.models import MessageRecord, SessionRecord, WorkItemRecord
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

            payload = build_search_payload(db_path, query="pipeline", limit=5)

            self.assertEqual(payload[0]["session_id"], "s1")
            self.assertEqual(payload[0]["html_path"], "C:/history/s1.html")

    def test_build_progress_payload_contains_implemented_and_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "index.sqlite"
            store = SessionStore(db_path)
            store.upsert_session(
                SessionRecord(
                    session_id="s2",
                    source="claude",
                    jsonl_path="/tmp/s2.jsonl",
                    html_path="C:/history/s2.html",
                    cwd="/tmp/agent-chat",
                    started_at="2026-06-12T15:00:00+09:00",
                    ended_at="2026-06-12T15:10:00+09:00",
                    messages=[],
                    work_items=[
                        WorkItemRecord(
                            project="agent-chat",
                            topic="pipeline",
                            status="in_progress",
                            summary="routing done, persistence pending",
                            implemented=["routing"],
                            pending=["persistence"],
                        )
                    ],
                )
            )

            payload = build_progress_payload(
                db_path,
                project="agent-chat",
                topic="pipeline",
                limit=5,
            )

            self.assertEqual(payload[0]["session_id"], "s2")
            self.assertIn("routing", payload[0]["implemented"])
            self.assertIn("persistence", payload[0]["pending"])


if __name__ == "__main__":
    unittest.main()

