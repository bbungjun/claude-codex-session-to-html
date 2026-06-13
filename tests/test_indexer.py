from pathlib import Path
import tempfile
import unittest

from session_memory.indexer import index_session, index_session_record
from session_memory.models import MessageRecord, SessionRecord
from session_memory.store import SessionStore


class IndexerTests(unittest.TestCase):
    def test_indexes_codex_fixture_and_extracts_work_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "index.sqlite"
            html_path = Path(tmp) / "codex.html"
            html_path.write_text("<html></html>", encoding="utf-8")

            record = index_session(
                "codex",
                Path("tests/fixtures/codex_pipeline.jsonl"),
                html_path,
                db_path,
            )

            store = SessionStore(db_path)
            rows = store.search_messages("pipeline")
            work_items = store.find_work_items(project="agent-chat", topic="pipeline")
            self.assertEqual(record.source, "codex")
            self.assertEqual(rows[0]["html_path"], str(html_path))
            self.assertTrue(work_items)
            self.assertIn("persistence", work_items[0]["pending"])

    def test_index_session_record_indexes_without_reparsing_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "index.sqlite"
            record = SessionRecord(
                session_id="record-1",
                source="codex",
                jsonl_path="/tmp/record-1.jsonl",
                html_path="/tmp/record-1.html",
                cwd="/tmp/app",
                started_at="2026-06-12T15:00:00+09:00",
                ended_at="2026-06-12T15:01:00+09:00",
                messages=[
                    MessageRecord(
                        "user",
                        "2026-06-12T15:00:00+09:00",
                        "record based indexing",
                        0,
                    )
                ],
            )

            result = index_session_record(record, db_path)

            self.assertEqual(result.record.session_id, "record-1")
            self.assertEqual(result.store_result.mode, "full")
            rows = SessionStore(db_path).search_messages("record")
            self.assertEqual(rows[0]["session_id"], "record-1")


if __name__ == "__main__":
    unittest.main()
