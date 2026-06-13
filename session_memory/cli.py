import argparse
import sys
from pathlib import Path

from session_memory.store import SessionStore
from session_memory.time_utils import has_time_reference, resolve_time_range, strip_time_terms


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="session-memory")
    subparsers = parser.add_subparsers(dest="command")

    search_parser = subparsers.add_parser("search")
    search_parser.add_argument("query")
    search_parser.add_argument("--db", required=True)
    search_parser.add_argument("--limit", type=int, default=10)
    search_parser.add_argument(
        "--when",
        default="",
        help="Optional time phrase such as '어제 3시' or 'yesterday 3pm'.",
    )

    progress_parser = subparsers.add_parser("progress")
    progress_parser.add_argument("--db", required=True)
    progress_parser.add_argument("--project", default="")
    progress_parser.add_argument("--topic", default="")
    progress_parser.add_argument("--limit", type=int, default=10)

    args = parser.parse_args(argv)
    if args.command == "search":
        return _search(args)
    if args.command == "progress":
        return _progress(args)
    parser.print_help()
    return 1


def _search(args) -> int:
    query = args.query
    time_query = args.when or query
    start = end = None
    if has_time_reference(time_query):
        start_dt, end_dt = resolve_time_range(time_query)
        start, end = start_dt.isoformat(), end_dt.isoformat()
        if not args.when:
            query = strip_time_terms(query)

    store = SessionStore(Path(args.db))
    rows = store.search_messages(query, limit=args.limit, start=start, end=end)
    for row in rows:
        print("{} | {} | {}".format(row["session_id"], row["source"], row["html_path"]))
        print("  {}".format(row["snippet"]))
    return 0


def _progress(args) -> int:
    store = SessionStore(Path(args.db))
    rows = store.find_work_items(project=args.project, topic=args.topic, limit=args.limit)
    for row in rows:
        print("{} | {} | {} | {}".format(row["session_id"], row["project"], row["topic"], row["html_path"]))
        if row.get("implemented"):
            print("  implemented: {}".format(", ".join(row["implemented"])))
        if row.get("pending"):
            print("  pending: {}".format(", ".join(row["pending"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

