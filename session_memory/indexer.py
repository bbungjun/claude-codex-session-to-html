from dataclasses import replace
from pathlib import Path
from typing import Union

from session_memory.extractors.work_items import extract_work_items
from session_memory.parsers.claude import parse_claude_jsonl
from session_memory.parsers.codex import parse_codex_jsonl
from session_memory.store import SessionStore


def index_session(
    source: str,
    jsonl_path: Union[str, Path],
    html_path: Union[str, Path],
    db_path: Union[str, Path],
):
    source_name = source.lower().strip()
    jsonl = Path(jsonl_path)
    html = Path(html_path)

    if source_name == "claude":
        record = parse_claude_jsonl(jsonl, html_path=str(html))
    elif source_name == "codex":
        record = parse_codex_jsonl(jsonl, html_path=str(html))
    else:
        raise ValueError("unsupported session source: {}".format(source))

    record = replace(record, work_items=extract_work_items(record))
    SessionStore(db_path).upsert_session(record)
    return record

