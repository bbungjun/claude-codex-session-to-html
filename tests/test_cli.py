import io
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest

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
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                exit_code = main(["search", "pipeline", "--db", str(db_path)])

            self.assertEqual(exit_code, 0)
            self.assertIn("s1", stdout.getvalue())
            self.assertIn("C:/history/s1.html", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()

