import json
from pathlib import Path
from typing import Any, List

from session_memory.models import MessageRecord, SessionRecord
from session_memory.time_utils import parse_timestamp


def parse_codex_jsonl(jsonl_path: Path, html_path: str) -> SessionRecord:
    path = Path(jsonl_path)
    messages: List[MessageRecord] = []
    cwd = ""
    timestamps: List[str] = []

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        event_type = obj.get("type", "")
        payload = obj.get("payload", {})
        timestamp = parse_timestamp(obj.get("timestamp", ""))

        if event_type == "session_meta":
            cwd = payload.get("cwd", cwd)
            continue

        parsed = _parse_codex_message(event_type, payload)
        if parsed is None:
            continue
        role, text = parsed
        if not text.strip():
            continue

        timestamps.append(timestamp)
        messages.append(
            MessageRecord(
                role=role,
                timestamp=timestamp,
                text=text.strip(),
                ordinal=len(messages),
            )
        )

    return SessionRecord(
        session_id=path.stem,
        source="codex",
        jsonl_path=str(path),
        html_path=str(html_path),
        cwd=cwd,
        started_at=timestamps[0] if timestamps else "",
        ended_at=timestamps[-1] if timestamps else "",
        messages=messages,
        summary=_make_summary(messages),
    )


def _parse_codex_message(event_type: str, payload: Any):
    if not isinstance(payload, dict):
        return None

    payload_type = payload.get("type", "")
    if event_type == "event_msg":
        if payload_type == "user_message":
            return "user", str(payload.get("message", ""))
        if payload_type == "agent_message":
            return "assistant", str(payload.get("message", ""))

    if event_type == "response_item":
        if payload_type == "function_call":
            name = payload.get("name", "tool")
            args = payload.get("arguments", {})
            if isinstance(args, (dict, list)):
                args_text = json.dumps(args, ensure_ascii=False)
            else:
                args_text = str(args)
            return "tool", "{} {}".format(name, args_text)
        if payload_type == "function_call_output":
            output = payload.get("output", "")
            if isinstance(output, (dict, list)):
                output = json.dumps(output, ensure_ascii=False)
            return "tool_result", str(output)

    return None


def _make_summary(messages: List[MessageRecord]) -> str:
    for message in messages:
        if message.role == "user" and message.text:
            return message.text[:160]
    return messages[0].text[:160] if messages else ""

