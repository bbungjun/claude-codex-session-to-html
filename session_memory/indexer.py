from dataclasses import replace
from dataclasses import dataclass
from pathlib import Path
from typing import Union

from session_memory.extractors.work_items import extract_work_items
from session_memory.parsers.claude import parse_claude_jsonl
from session_memory.parsers.codex import parse_codex_jsonl
from session_memory.models import SessionRecord
from session_memory.store import SessionStore, StoreUpsertResult


@dataclass(frozen=True)
class IndexSessionResult:
    record: SessionRecord
    store_result: StoreUpsertResult


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

    return index_session_record(record, db_path).record


def index_session_record(
    record: SessionRecord,
    db_path: Union[str, Path],
) -> IndexSessionResult:
    indexed_record = replace(record, work_items=extract_work_items(record))
    jsonl_size, jsonl_mtime = _jsonl_metadata(indexed_record.jsonl_path)
    store_result = SessionStore(db_path).upsert_session(
        indexed_record,
        jsonl_size=jsonl_size,
        jsonl_mtime=jsonl_mtime,
    )
    return IndexSessionResult(record=indexed_record, store_result=store_result)


def _jsonl_metadata(jsonl_path: Union[str, Path]):
    try:
        stat = Path(jsonl_path).stat()
    except OSError:
        return 0, 0.0
    return stat.st_size, stat.st_mtime
