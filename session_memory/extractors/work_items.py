import re
from pathlib import Path
from typing import Iterable, List

from session_memory.models import SessionRecord, WorkItemRecord


IMPLEMENTED_HINTS = (
    "구현",
    "완료",
    "만들",
    "created",
    "implemented",
    "added",
    "finished",
    "done",
)
PENDING_HINTS = (
    "남았",
    "아직",
    "해야",
    "todo",
    "pending",
    "remaining",
    "not yet",
)
TOPIC_KEYWORDS = (
    "pipeline",
    "routing",
    "persistence",
    "retry",
    "streaming",
    "mcp",
    "index",
    "watcher",
    "html",
    "parser",
    "queue",
    "stack",
)


def extract_work_items(record: SessionRecord) -> List[WorkItemRecord]:
    evidence = [
        message
        for message in record.messages
        if message.role == "assistant"
        and not _looks_like_tool_payload(message.text)
        and _looks_like_development_progress(message.text)
    ]
    if not evidence:
        return []

    combined = "\n".join(message.text for message in evidence)
    implemented = _unique(_extract_implemented(combined))
    pending = _unique(_extract_pending(combined))
    if not implemented and not pending:
        return []

    files = _unique(_extract_files(combined))
    topic_context = "\n".join(
        message.text
        for message in record.messages
        if message.role in ("user", "assistant")
        and not _looks_like_tool_payload(message.text)
    )
    topics = _extract_topics(topic_context)
    project = _project_from_record(record, combined)
    status = "in_progress" if pending else ("completed" if implemented else "mentioned")
    summary = _summarize(combined)

    return [
        WorkItemRecord(
            project=project,
            topic=topic,
            status=status,
            summary=summary,
            implemented=implemented,
            pending=pending,
            files=files,
            evidence_message_ordinals=[message.ordinal for message in evidence],
        )
        for topic in topics
    ]


def _looks_like_development_progress(text: str) -> bool:
    lowered = text.lower()
    return any(hint in lowered for hint in IMPLEMENTED_HINTS + PENDING_HINTS + TOPIC_KEYWORDS)


def _looks_like_tool_payload(text: str) -> bool:
    stripped = text.lstrip()
    return (
        stripped.startswith("Wall time:")
        or stripped.startswith("Output:")
        or '"type":"text"' in stripped
        or '"session_id"' in stripped
        or '"html_path"' in stripped
    )


def _project_from_record(record: SessionRecord, text: str) -> str:
    if record.cwd:
        return Path(record.cwd).name or record.cwd
    match = re.search(r"\b([a-z][a-z0-9_-]*(?:\s+chat\s+bot)?)\b", text.lower())
    return match.group(1).replace(" ", "-") if match else ""


def _extract_topics(text: str) -> List[str]:
    lowered = text.lower()
    topics = [keyword for keyword in TOPIC_KEYWORDS if keyword in lowered]
    return _unique(topics) or ["general"]


def _extract_implemented(text: str) -> List[str]:
    results: List[str] = []
    patterns = [
        r"([^.。\n]+?)(?:까지\s*)?구현(?:했|했습니다|했어요|했다|됐|되었습니다|됨|되어| 완료)",
        r"implemented\s+([^.。\n]+)",
        r"([^.。\n:]+?)\s+implemented",
        r"added\s+([^.。\n]+)",
        r"finished\s+([^.。\n]+)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            results.extend(_split_items(match.group(1)))
    return _clean_items(results)


def _extract_pending(text: str) -> List[str]:
    results: List[str] = []
    patterns = [
        r"([^.。\n]+?)(?:는|은|이|가)?\s*(?:아직\s*)?남았(?:습니다|다|어요)?",
        r"(?:pending|remaining|todo)[:\s]+([^.。\n]+)",
        r"([^.。\n:]+?)\s+pending",
        r"([^.。\n]+?)\s+(?:is|are)\s+pending",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            results.extend(_split_items(match.group(1)))
    return _clean_items(results)


def _extract_files(text: str) -> List[str]:
    return re.findall(r"[\w./\\-]+\.(?:py|js|ts|tsx|jsx|md|json|sh|sqlite|html)", text)


def _split_items(value: str) -> Iterable[str]:
    value = re.sub(r"\b(and|with)\b", ",", value, flags=re.IGNORECASE)
    value = value.replace("와", ",").replace("과", ",").replace("및", ",")
    value = value.replace("하고", ",").replace("그리고", ",")
    return [part.strip(" ,.-") for part in re.split(r"[,/]", value) if part.strip(" ,.-")]


def _clean_items(items: Iterable[str]) -> List[str]:
    cleaned = []
    for item in items:
        text = re.sub(r"\s+", " ", item).strip()
        text = re.sub(r"^(했습니다|했습니다\.|은|는|이|가)\s*", "", text)
        text = _trim_topic_prefix(text)
        if 2 <= len(text) <= 120:
            cleaned.append(text)
    return _unique(cleaned)


def _trim_topic_prefix(text: str) -> str:
    parts = text.split()
    if len(parts) >= 2 and parts[0].lower().rstrip(":") in TOPIC_KEYWORDS:
        return " ".join(parts[1:]).strip()
    return text


def _unique(items: Iterable[str]) -> List[str]:
    result = []
    seen = set()
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _summarize(text: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact[:240]
