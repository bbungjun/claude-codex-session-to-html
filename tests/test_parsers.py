from pathlib import Path
import unittest

from session_memory.models import MessageRecord, SessionRecord
from session_memory.parsers.claude import parse_claude_jsonl
from session_memory.parsers.codex import parse_codex_jsonl


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


if __name__ == "__main__":
    unittest.main()

