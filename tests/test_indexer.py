from pathlib import Path
import tempfile
import unittest

from session_memory.indexer import index_session
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


if __name__ == "__main__":
    unittest.main()

