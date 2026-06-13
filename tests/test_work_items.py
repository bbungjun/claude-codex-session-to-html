import unittest

from session_memory.extractors.work_items import extract_work_items
from session_memory.models import MessageRecord, SessionRecord


class WorkItemExtractorTests(unittest.TestCase):
    def test_ignores_tool_result_payloads_when_extracting_progress(self):
        record = SessionRecord(
            session_id="s1",
            source="codex",
            jsonl_path="/tmp/s1.jsonl",
            html_path="/tmp/s1.html",
            cwd="/home/me/agent-chat",
            started_at="2026-06-14T02:44:00+09:00",
            ended_at="2026-06-14T02:45:00+09:00",
            messages=[
                MessageRecord(
                    role="tool_result",
                    timestamp="2026-06-14T02:44:30+09:00",
                    text=(
                        'Wall time: 4.1878 seconds\n'
                        'Output:\n'
                        '[{"type":"text","text":"{\\n'
                        '  \\"session_id\\": \\"rollout-123\\",\\n'
                        '  \\"html_path\\": \\"/mnt/c/Users/PC/Desktop/session_history/a.html\\",\\n'
                        '  \\"summary\\": \\"pipeline 구현 완료, persistence 남았습니다\\"\\n'
                        '}"}]'
                    ),
                    ordinal=0,
                )
            ],
        )

        self.assertEqual(extract_work_items(record), [])

    def test_extracts_progress_from_assistant_summary(self):
        record = SessionRecord(
            session_id="s2",
            source="codex",
            jsonl_path="/tmp/s2.jsonl",
            html_path="/tmp/s2.html",
            cwd="/home/me/agent-chat",
            started_at="2026-06-14T02:44:00+09:00",
            ended_at="2026-06-14T02:45:00+09:00",
            messages=[
                MessageRecord(
                    role="assistant",
                    timestamp="2026-06-14T02:44:30+09:00",
                    text=(
                        "pipeline routing implemented. "
                        "persistence pending."
                    ),
                    ordinal=0,
                )
            ],
        )

        items = extract_work_items(record)

        self.assertEqual(items[0].topic, "pipeline")
        self.assertIn("routing", items[0].implemented)
        self.assertIn("persistence", items[0].pending)

    def test_ignores_search_intent_that_mentions_progress_terms(self):
        record = SessionRecord(
            session_id="s3",
            source="codex",
            jsonl_path="/tmp/s3.jsonl",
            html_path="/tmp/s3.html",
            cwd="/home/me",
            started_at="2026-06-14T02:44:00+09:00",
            ended_at="2026-06-14T02:45:00+09:00",
            messages=[
                MessageRecord(
                    role="assistant",
                    timestamp="2026-06-14T02:44:30+09:00",
                    text=(
                        "6월 13일 세션들 중 aws가 언급된 기록을 "
                        "local-dev-memory에서 찾아보고, 구현 진행 항목이 "
                        "따로 추출돼 있는지도 같이 확인하겠습니다."
                    ),
                    ordinal=0,
                )
            ],
        )

        self.assertEqual(extract_work_items(record), [])


if __name__ == "__main__":
    unittest.main()
