import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from session_memory.store import SessionStore
from session_memory.time_utils import has_time_reference, resolve_time_range, strip_time_terms


def build_search_payload(
    db_path: Union[Path, str],
    query: str,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    search_query = query
    start = end = None
    if has_time_reference(query):
        start_dt, end_dt = resolve_time_range(query)
        start, end = start_dt.isoformat(), end_dt.isoformat()
        search_query = strip_time_terms(query)
    return SessionStore(Path(db_path)).search_messages(
        search_query,
        limit=limit,
        start=start,
        end=end,
    )


def build_session_payload(
    db_path: Union[Path, str],
    session_id: str,
) -> Optional[Dict[str, Any]]:
    return SessionStore(Path(db_path)).get_session(session_id)


def build_progress_payload(
    db_path: Union[Path, str],
    project: str = "",
    topic: str = "",
    limit: int = 10,
) -> List[Dict[str, Any]]:
    return SessionStore(Path(db_path)).find_work_items(
        project=project,
        topic=topic,
        limit=limit,
    )


def create_server():
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError("MCP support requires: pip install mcp") from exc

    db_path = Path(os.environ.get("SESSION_MEMORY_DB", "index.sqlite"))
    mcp = FastMCP("local-dev-memory")

    @mcp.tool()
    def search_sessions(query: str, limit: int = 10):
        """Search local Claude/Codex session history and return HTML paths."""
        return build_search_payload(db_path, query=query, limit=limit)

    @mcp.tool()
    def get_session(session_id: str):
        """Return one indexed session by id."""
        return build_session_payload(db_path, session_id=session_id)

    @mcp.tool()
    def get_project_progress(project: str = "", topic: str = "", limit: int = 10):
        """Return implementation progress extracted from local development sessions."""
        return build_progress_payload(db_path, project=project, topic=topic, limit=limit)

    @mcp.resource("session://{session_id}")
    def session_resource(session_id: str):
        session = build_session_payload(db_path, session_id=session_id)
        return session or {"error": "session not found: {}".format(session_id)}

    return mcp


def main() -> None:
    create_server().run()


if __name__ == "__main__":
    main()

