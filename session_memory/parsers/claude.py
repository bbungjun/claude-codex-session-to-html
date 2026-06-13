import json
from pathlib import Path
from typing import Any, List

from session_memory.models import MessageRecord, SessionRecord
from session_memory.time_utils import parse_timestamp


def parse_claude_jsonl(jsonl_path: Path, html_path: str) -> SessionRecord:
    path = Path(jsonl_path)
    messages: List[MessageRecord] = []
    session_id = path.stem
    cwd = ""
    timestamps: List[str] = []

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        msg_type = obj.get("type", "")
        if msg_type not in ("user", "assistant"):
            continue

        text = _extract_claude_text(obj.get("message", {}).get("content", ""))
        if not text.strip():
            continue

        timestamp = parse_timestamp(obj.get("timestamp", ""))
        session_id = obj.get("sessionId") or obj.get("session_id") or session_id
        cwd = obj.get("cwd", cwd)
        timestamps.append(timestamp)
        messages.append(
            MessageRecord(
                role="assistant" if msg_type == "assistant" else "user",
                timestamp=timestamp,
                text=text.strip(),
                ordinal=len(messages),
            )
        )

    return SessionRecord(
        session_id=session_id,
        source="claude",
        jsonl_path=str(path),
        html_path=str(html_path),
        cwd=cwd,
        started_at=timestamps[0] if timestamps else "",
        ended_at=timestamps[-1] if timestamps else "",
        messages=messages,
        summary=_make_summary(messages),
    )


def _extract_claude_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type == "text":
                parts.append(str(item.get("text", "")))
            elif item_type == "tool_result":
                parts.append(_extract_tool_result_text(item.get("content", "")))
        return "\n".join(part for part in parts if part)
    return str(content)


def _extract_tool_result_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            str(item.get("text", ""))
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        )
    return str(content)


def _make_summary(messages: List[MessageRecord]) -> str:
    for message in messages:
        if message.role == "user" and message.text:
            return message.text[:160]
    return messages[0].text[:160] if messages else ""

