from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path
from typing import Sequence

from ai_memory.core.config import init_home
from ai_memory.core.models import MemoryCandidate, MemoryRecord
from ai_memory.retrieval.assembler import assemble_context, hook_json
from ai_memory.retrieval.ranking import rank_records
from ai_memory.review.queue import ReviewQueue
from ai_memory.store.sqlite import SQLiteMemoryStore


def _tokenize(value: str) -> tuple[str, ...]:
    seen: list[str] = []
    for token in re.findall(r"[a-z0-9_-]+", value.lower()):
        if token not in seen:
            seen.append(token)
    return tuple(seen)


def _init_store(home: Path) -> tuple[SQLiteMemoryStore, object]:
    config = init_home(home)
    store = SQLiteMemoryStore(config.store_path)
    store.initialize()
    return store, config


def _search_records(store: SQLiteMemoryStore, query: str, limit: int) -> list[MemoryRecord]:
    if not query.strip():
        return []
    tokens = _tokenize(query)
    seen: set[str] = set()
    records: list[MemoryRecord] = []
    for token in tokens:
        try:
            matches = store.search(token, limit=limit)
        except sqlite3.OperationalError:
            continue
        for record in matches:
            if record.id not in seen:
                seen.add(record.id)
                records.append(record)
    return records[:limit]


def adapter_for(client: str, home: Path):
    if client == "claude-code":
        from ai_memory.adapters.claude_code import ClaudeCodeAdapter
        return ClaudeCodeAdapter(home=home)
    if client == "codex-cli":
        from ai_memory.adapters.codex_cli import CodexCliAdapter
        return CodexCliAdapter(home=home)
    if client == "gemini-cli":
        from ai_memory.adapters.gemini_cli import GeminiCliAdapter
        return GeminiCliAdapter(home=home)
    raise ValueError(f"Unsupported client: {client}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-memory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize local ai-memory storage")
    init_parser.add_argument("--home", type=Path, default=Path.home() / ".ai-memory")

    add_parser = subparsers.add_parser("add", help="Add a memory record")
    add_parser.add_argument("uri")
    add_parser.add_argument("content")
    add_parser.add_argument("--home", type=Path, default=Path.home() / ".ai-memory")
    add_parser.add_argument("--type", default="project_command")
    add_parser.add_argument("--scope", default="project")

    search_parser = subparsers.add_parser("search", help="Search stored memories")
    search_parser.add_argument("query")
    search_parser.add_argument("--home", type=Path, default=Path.home() / ".ai-memory")
    search_parser.add_argument("--limit", type=int, default=12)

    context_parser = subparsers.add_parser("context", help="Build retrieval context")
    context_parser.add_argument("--home", type=Path, default=Path.home() / ".ai-memory")
    context_parser.add_argument("--prompt", default="memory")
    context_parser.add_argument("--format", choices=("markdown", "hook-json"), default="markdown")
    context_parser.add_argument("--event", default="SessionStart")

    discover_parser = subparsers.add_parser("discover", help="Discover client transcript sources")
    discover_parser.add_argument("--client", required=True)
    discover_parser.add_argument("--home", type=Path, default=Path.home())

    review_parser = subparsers.add_parser("review", help="List pending review items")
    review_parser.add_argument("--home", type=Path, default=Path.home() / ".ai-memory")

    approve_parser = subparsers.add_parser("approve", help="Approve a review item")
    approve_parser.add_argument("review_id")
    approve_parser.add_argument("--home", type=Path, default=Path.home() / ".ai-memory")

    reject_parser = subparsers.add_parser("reject", help="Reject a review item")
    reject_parser.add_argument("review_id")
    reject_parser.add_argument("--home", type=Path, default=Path.home() / ".ai-memory")

    import_parser = subparsers.add_parser("import", help="Archive a transcript")
    import_parser.add_argument("--client", required=True)
    import_parser.add_argument("--path", type=Path, required=True)
    import_parser.add_argument("--home", type=Path, default=Path.home() / ".ai-memory")
    import_parser.add_argument("--archive-only", action="store_true")

    mcp_parser = subparsers.add_parser("mcp", help="Run MCP server commands")
    mcp_subparsers = mcp_parser.add_subparsers(dest="mcp_command", required=True)
    mcp_subparsers.add_parser("serve", help="Serve ai-memory MCP tools")

    return parser


def run(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        config = init_home(args.home)
        store = SQLiteMemoryStore(config.store_path)
        store.initialize()
        print(f"Initialized ai-memory at {config.home}")
        return 0

    if args.command == "add":
        store, _ = _init_store(args.home)
        tokens = _tokenize(args.content)
        record = store.create_memory(
            MemoryCandidate(
                uri=args.uri,
                type=args.type,
                scope=args.scope,
                content=args.content,
                summary=args.content,
                confidence=1.0,
                risk="low",
                evidence="manual CLI add",
                tags=tokens,
                triggers=tokens,
            ),
            status="approved",
            change_reason="manual CLI add",
        )
        print(f"Added memory {record.id}")
        return 0

    if args.command == "search":
        store, _ = _init_store(args.home)
        for record in _search_records(store, args.query, args.limit):
            print(record.id, record.uri, record.content)
        return 0

    if args.command == "context":
        store, config = _init_store(args.home)
        records = rank_records(_search_records(store, args.prompt, config.retrieval_max_items))[: config.retrieval_max_items]
        context = assemble_context(records)
        if args.format == "hook-json":
            print(json.dumps(hook_json(args.event, context)))
        else:
            print(context)
        return 0

    if args.command == "discover":
        try:
            adapter = adapter_for(args.client, args.home)
        except ValueError as error:
            parser.error(str(error))
        for source in adapter.discover():
            print(source)
        return 0

    if args.command == "review":
        queue = ReviewQueue(args.home / "review-queue.jsonl")
        items = queue.list_pending()
        if not items:
            print("No pending review items")
            return 0
        for item in items:
            print(f"{item.id} {item.candidate.uri} {item.reason}")
        return 0

    if args.command == "approve":
        try:
            ReviewQueue(args.home / "review-queue.jsonl").mark(args.review_id, "approved")
        except ValueError as error:
            print(error)
            return 2
        print(f"Approved {args.review_id}")
        return 0

    if args.command == "reject":
        try:
            ReviewQueue(args.home / "review-queue.jsonl").mark(args.review_id, "rejected")
        except ValueError as error:
            print(error)
            return 2
        print(f"Rejected {args.review_id}")
        return 0

    if args.command == "import":
        if args.client != "generic":
            print("Only generic import is supported by this command in the first version")
            return 2
        if not args.archive_only:
            print("--archive-only is required for import")
            return 2
        source = args.path
        if not source.is_file():
            print(f"Transcript path is not a file: {source}")
            return 2
        raw_dir = args.home / "raw" / "generic"
        target = raw_dir / source.name
        if target.exists():
            print(f"Archived transcript already exists: {target}")
            return 2
        try:
            content = source.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            print(f"Transcript must be UTF-8 text: {source}")
            return 2
        raw_dir.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        print(f"Transcript archived at {target}")
        return 0

    if args.command == "mcp" and args.mcp_command == "serve":
        from ai_memory.mcp.server import main as mcp_main

        mcp_main()
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


def main() -> None:
    raise SystemExit(run())
