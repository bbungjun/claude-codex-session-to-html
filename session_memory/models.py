from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class MessageRecord:
    role: str
    timestamp: str
    text: str
    ordinal: int


@dataclass(frozen=True)
class WorkItemRecord:
    project: str
    topic: str
    status: str
    summary: str
    implemented: List[str] = field(default_factory=list)
    pending: List[str] = field(default_factory=list)
    files: List[str] = field(default_factory=list)
    evidence_message_ordinals: List[int] = field(default_factory=list)


@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    source: str
    jsonl_path: str
    html_path: str
    cwd: str
    started_at: str
    ended_at: str
    messages: List[MessageRecord]
    summary: str = ""
    work_items: List[WorkItemRecord] = field(default_factory=list)

