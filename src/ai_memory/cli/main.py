from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path
from typing import Sequence

from ai_memory.core.config import AppConfig, init_home, load_config
from ai_memory.core.models import MemoryCandidate, MemoryRecord
from ai_memory.core.uri import parse_memory_uri
from ai_memory.extraction.validator import validate_candidate
from ai_memory.privacy.redactor import redact_secrets
from ai_memory.privacy.sensitive_paths import is_sensitive_path
from ai_memory.mcp.tools import memory_context as build_memory_context
from ai_memory.mcp.tools import memory_search as search_memory
from ai_memory.retrieval.assembler import hook_json
from ai_memory.retrieval.environment import detect_environment
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


def _repo_id_from_uri(uri: str) -> str | None:
    parsed = parse_memory_uri(uri)
    if parsed.namespace in {"project", "branch", "path"}:
        return parsed.authority
    return None


def _dry_run_config(home: Path) -> AppConfig:
    return AppConfig(
        home=home,
        store_path=home / "memory.db",
        raw_dir=home / "raw",
        log_dir=home / "logs",
        review_queue_path=home / "review-queue.jsonl",
        extractor_provider=None,
        extractor_command=None,
        max_input_chars=60000,
        retrieval_max_items=12,
        retrieval_max_chars=6000,
        auto_write_confidence=0.85,
        redact_secrets=True,
        confirm_sensitive_sources=True,
    )


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
    context_parser.add_argument("--path", dest="relative_path")

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
    import_parser.add_argument("--allow-sensitive-source", action="store_true")
    import_parser.add_argument("--redact-archive", action="store_true")

    history_parser = subparsers.add_parser("history", help="Historical transcript initialization")
    history_subparsers = history_parser.add_subparsers(dest="history_command", required=True)
    history_init = history_subparsers.add_parser("init", help="Initialize memories from historical transcripts")
    history_init.add_argument("--home", type=Path, default=Path.home() / ".ai-memory")
    history_init.add_argument("--source-home", type=Path, default=Path.home())
    history_init.add_argument("--clients", default="all")
    history_init.add_argument("--review-only", action="store_true")
    history_init.add_argument("--auto-write-low-risk", action="store_true")
    history_init.add_argument("--limit", type=int)
    history_init.add_argument("--dry-run", action="store_true")
    history_init.add_argument("--include-generic", type=Path, action="append", default=[])
    history_init.add_argument("--allow-sensitive-source", action="store_true")
    history_init.add_argument("--redact-archive", action="store_true")

    mcp_parser = subparsers.add_parser("mcp", help="Run MCP server commands")
    mcp_subparsers = mcp_parser.add_subparsers(dest="mcp_command", required=True)
    mcp_subparsers.add_parser("serve", help="Serve ai-memory MCP tools")

    web_parser = subparsers.add_parser("web", help="Start web dashboard")
    web_parser.add_argument("--host", default="127.0.0.1")
    web_parser.add_argument("--port", type=int, default=8080)
    web_parser.add_argument("--home", type=Path, default=Path.home() / ".ai-memory")

    capture_parser = subparsers.add_parser("capture", help="Capture and process a transcript")
    capture_parser.add_argument("--client", required=True)
    capture_parser.add_argument("--home", type=Path, default=Path.home() / ".ai-memory")
    capture_parser.add_argument("--source-home", type=Path, default=Path.home())
    capture_parser.add_argument("--session", help="specific session file path")
    capture_parser.add_argument("--no-archive", action="store_true")
    capture_parser.add_argument("--no-extract", action="store_true")
    capture_parser.add_argument("--review-only", action="store_true")
    capture_parser.add_argument("--auto-write-low-risk", action="store_true")
    capture_parser.add_argument("--redact-archive", action="store_true")

    wiki_parser = subparsers.add_parser("wiki", help="Export memories to wiki projection")
    wiki_parser.add_argument("--home", type=Path, default=Path.home() / ".ai-memory")
    wiki_parser.add_argument("--output-dir", type=Path, default=None)
    wiki_parser.add_argument("--include-auto-approved", action="store_true")
    wiki_parser.add_argument("--types", type=str, default=None)

    system_parser = subparsers.add_parser("system", help="System memory commands")
    system_subparsers = system_parser.add_subparsers(dest="system_command", required=True)
    system_init = system_subparsers.add_parser("init", help="Seed system memory bootstrapping records")
    system_init.add_argument("--home", type=Path, default=Path.home() / ".ai-memory")
    system_init.add_argument("--force", action="store_true", help="Re-seed even existing system memories")

    memory_parser = subparsers.add_parser("memory", help="Memory inspection and update commands")
    memory_subparsers = memory_parser.add_subparsers(dest="memory_command", required=True)
    memory_show = memory_subparsers.add_parser("show", help="Show memory details")
    memory_show.add_argument("memory_id")
    memory_show.add_argument("--home", type=Path, default=Path.home() / ".ai-memory")
    memory_list = memory_subparsers.add_parser("list", help="List memories")
    memory_list.add_argument("--home", type=Path, default=Path.home() / ".ai-memory")
    memory_list.add_argument("--status", type=str, default=None, help="Filter by status (approved,auto_approved,proposed,rejected)")
    memory_list.add_argument("--uri", type=str, default=None, help="Filter by URI pattern")
    memory_list.add_argument("--limit", type=int, default=50)
    memory_update = memory_subparsers.add_parser("update", help="Update memory content")
    memory_update.add_argument("memory_id")
    memory_update.add_argument("new_content", nargs="+", help="New content text")
    memory_update.add_argument("--home", type=Path, default=Path.home() / ".ai-memory")

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
        environment = detect_environment(Path.cwd(), client="cli", prompt=args.content)
        candidate = MemoryCandidate(
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
            repo_id=environment["repo_id"] or _repo_id_from_uri(args.uri),
        )
        try:
            validate_candidate(candidate)
        except ValueError as error:
            print(error)
            return 2
        record = store.create_memory(
            candidate,
            status="approved",
            change_reason="manual CLI add",
        )
        print(f"Added memory {record.id}")
        return 0

    if args.command == "search":
        store, _ = _init_store(args.home)
        environment = detect_environment(Path.cwd(), client="cli", prompt=args.query)
        result = search_memory(store, args.query, args.limit, environment)
        for item in result["items"]:
            print(item["id"], item["uri"], item["content"])
        return 0

    if args.command == "context":
        store, config = _init_store(args.home)
        environment = detect_environment(Path.cwd(), client="cli", prompt=args.prompt)
        environment["relative_path"] = args.relative_path
        result = build_memory_context(store, args.prompt, config.retrieval_max_items, environment)
        context = result["context"]
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
        config = load_config(args.home)
        queue = ReviewQueue(config.review_queue_path)
        items = queue.list_pending()
        if not items:
            print("No pending review items")
            return 0
        for item in items:
            print(f"{item.id} {item.candidate.uri} {item.reason}")
        return 0

    if args.command == "approve":
        config = load_config(args.home)
        store = SQLiteMemoryStore(config.store_path)
        store.initialize()
        queue = ReviewQueue(config.review_queue_path)
        try:
            item = queue.get_pending(args.review_id)
            validate_candidate(item.candidate)
            existing = store.get_by_uri(item.candidate.uri)
            if existing is None:
                store.create_memory(item.candidate, status="approved", change_reason=f"approved review item {item.id}")
            elif existing.content != item.candidate.content:
                print(f"Conflicting memory already exists for URI: {item.candidate.uri}")
                return 2
            else:
                store.append_source(existing.id, item.candidate)
            queue.mark(args.review_id, "approved")
        except ValueError as error:
            print(error)
            return 2
        print(f"Approved {args.review_id}")
        return 0

    if args.command == "reject":
        config = load_config(args.home)
        try:
            ReviewQueue(config.review_queue_path).mark(args.review_id, "rejected")
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
        try:
            resolved_source = source.resolve(strict=True)
        except OSError as error:
            print(f"Unable to resolve transcript path: {source}: {error}")
            return 2
        if (is_sensitive_path(source) or is_sensitive_path(resolved_source)) and not args.allow_sensitive_source:
            print(f"Refusing to archive sensitive path without --allow-sensitive-source: {source}")
            return 2
        raw_dir = args.home / "raw" / "generic"
        target = raw_dir / source.name
        if target.exists():
            print(f"Archived transcript already exists: {target}")
            return 2
        try:
            content = resolved_source.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            print(f"Transcript must be UTF-8 text: {source}")
            return 2
        raw_dir.mkdir(parents=True, exist_ok=True)
        if args.redact_archive:
            content = redact_secrets(content)
        target.write_text(content, encoding="utf-8")
        print(f"Transcript archived at {target}")
        return 0

    if args.command == "history" and args.history_command == "init":
        from ai_memory.extraction.providers.command import CommandExtractorProvider
        from ai_memory.history.initializer import HistoryInitOptions, parse_clients, run_history_init

        try:
            clients = parse_clients(args.clients)
            review_only = args.review_only or not args.auto_write_low_risk
            options = HistoryInitOptions(
                clients=clients,
                include_generic=tuple(args.include_generic),
                review_only=review_only,
                auto_write_low_risk=args.auto_write_low_risk,
                limit=args.limit,
                dry_run=args.dry_run,
                allow_sensitive_source=args.allow_sensitive_source,
                redact_archive=args.redact_archive,
            )
        except ValueError as error:
            try:
                parser.error(str(error))
            except SystemExit as exit_error:
                return int(exit_error.code)

        if args.dry_run:
            config = _dry_run_config(args.home)
            store = SQLiteMemoryStore(config.store_path)
            queue = ReviewQueue(config.review_queue_path)
            extractor = None
        else:
            config = load_config(args.home)
            store = SQLiteMemoryStore(config.store_path)
            store.initialize()
            queue = ReviewQueue(config.review_queue_path)
            extractor = None
            if config.extractor_provider == "command" and config.extractor_command:
                extractor = CommandExtractorProvider(config.extractor_command)
        summary = run_history_init(
            options=options,
            config=config,
            source_home=args.source_home,
            store=store,
            queue=queue,
            extractor=extractor,
        )
        _print_history_summary(summary, config.raw_dir, args.dry_run)
        return 0

    if args.command == "mcp" and args.mcp_command == "serve":
        from ai_memory.mcp.server import main as mcp_main

        mcp_main()
        return 0

    if args.command == "web":
        from ai_memory.web.dashboard import run_server
        run_server(host=args.host, port=args.port)
        return 0

    if args.command == "capture":
        from ai_memory.cli.capture import run_capture

        return run_capture(
            client=args.client,
            home=args.home,
            source_home=args.source_home,
            session_path=args.session,
            no_archive=args.no_archive,
            no_extract=args.no_extract,
            review_only=args.review_only,
            auto_write_low_risk=args.auto_write_low_risk,
            redact_archive=args.redact_archive,
        )

    if args.command == "wiki":
        from ai_memory.cli.wiki import run_wiki

        types = None
        if args.types:
            types = tuple(t.strip() for t in args.types.split(",") if t.strip())
        return run_wiki(
            home=args.home,
            output_dir=args.output_dir,
            include_auto_approved=args.include_auto_approved,
            types=types,
        )

    if args.command == "system" and args.system_command == "init":
        from ai_memory.system.init import seed_system_memories

        store, _ = _init_store(args.home)
        seeded, skipped = seed_system_memories(store)
        if args.force:
            print(f"System memory seeded: {seeded} new, {skipped} existing (force re-seed)")
        else:
            print(f"System memory seeded: {seeded} new, {skipped} existing (skipped existing)")
        return 0

    if args.command == "memory":
        from ai_memory.cli.update import list_memories, show_memory, update_memory

        if args.memory_command == "show":
            code, output = show_memory(memory_id=args.memory_id, home=args.home)
            print(output)
            return code

        if args.memory_command == "list":
            status_filter = None
            if args.status:
                status_filter = tuple(s.strip() for s in args.status.split(",") if s.strip())
            code, output = list_memories(home=args.home, status_filter=status_filter, uri_pattern=args.uri, limit=args.limit)
            print(output)
            return code

        if args.memory_command == "update":
            new_content = " ".join(args.new_content)
            code, output = update_memory(memory_id=args.memory_id, new_content=new_content, home=args.home)
            print(output)
            return code

    parser.error(f"Unknown command: {args.command}")
    return 2


def _print_history_summary(summary: object, raw_dir: Path, dry_run: bool) -> None:
    print("Historical initialization complete.")
    print()
    print(f"Clients scanned: {summary.clients_scanned}")
    print(f"Sources found: {summary.sources_found}")
    print(f"Sources processed: {summary.sources_processed}")
    print(f"Transcripts archived: {summary.transcripts_archived}")
    print(f"Transcripts skipped: {summary.transcripts_skipped}")
    print(f"Extraction skipped: {summary.extraction_skipped}")
    print(f"Candidates extracted: {summary.candidates_extracted}")
    print(f"Review queued: {summary.review_queued}")
    print(f"Auto-written: {summary.auto_written}")
    print(f"Discarded: {summary.discarded}")
    print(f"Errors: {len(summary.errors)}")
    print()
    if dry_run:
        print("Dry run only. No archives, review items, or memories were written.")
    else:
        print(f"Raw transcripts were archived under: {raw_dir}")
        print("Raw archives may contain original private content.")
        print("Review candidates with: ai-memory review")
    for error in summary.errors:
        print(f"Error: {error}")


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
