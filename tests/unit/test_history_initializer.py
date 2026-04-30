from pathlib import Path

import pytest

from ai_memory.core.config import init_home
from ai_memory.history.initializer import (
    BUILT_IN_CLIENTS,
    HistoryInitOptions,
    HistorySource,
    archive_target_for,
    collect_generic_sources,
    parse_clients,
    run_history_init,
)
from ai_memory.review.queue import ReviewQueue
from ai_memory.store.sqlite import SQLiteMemoryStore


def test_parse_clients_all_resolves_built_ins():
    assert parse_clients("all") == BUILT_IN_CLIENTS


def test_parse_clients_accepts_comma_separated_subset():
    assert parse_clients("claude-code,gemini-cli") == ("claude-code", "gemini-cli")


def test_parse_clients_rejects_unknown_client():
    with pytest.raises(ValueError, match="Unsupported history client: unknown"):
        parse_clients("claude-code,unknown")


def test_history_options_reject_conflicting_routing_modes():
    with pytest.raises(ValueError, match="mutually exclusive"):
        HistoryInitOptions(
            clients=("claude-code",),
            include_generic=(),
            review_only=True,
            auto_write_low_risk=True,
            limit=None,
            dry_run=False,
        )


def test_collect_generic_sources_accepts_file_and_directory_and_skips_hidden(tmp_path: Path):
    direct = tmp_path / "chat.md"
    direct.write_text("User: remember pytest", encoding="utf-8")
    root = tmp_path / "logs"
    hidden_dir = root / ".hidden"
    hidden_dir.mkdir(parents=True)
    nested = root / "nested.jsonl"
    nested.write_text("{}\n", encoding="utf-8")
    ignored_suffix = root / "image.bin"
    ignored_suffix.write_bytes(b"\x00\x01")
    hidden_file = root / ".secret.md"
    hidden_file.write_text("hidden", encoding="utf-8")
    hidden_nested = hidden_dir / "chat.md"
    hidden_nested.write_text("hidden", encoding="utf-8")

    sources = collect_generic_sources((direct, root))

    assert sources == [HistorySource(client="generic", path=direct), HistorySource(client="generic", path=nested)]


def test_archive_target_for_uses_stable_suffix_for_duplicate_names(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    source_a = tmp_path / "a" / "session.jsonl"
    source_b = tmp_path / "b" / "session.jsonl"
    source_a.parent.mkdir()
    source_b.parent.mkdir()
    source_a.write_text("a", encoding="utf-8")
    source_b.write_text("b", encoding="utf-8")

    first = archive_target_for(raw_dir, HistorySource("claude-code", source_a))
    first.parent.mkdir(parents=True)
    first.write_text("archived", encoding="utf-8")
    second = archive_target_for(raw_dir, HistorySource("claude-code", source_b))

    assert first == raw_dir / "claude-code" / "session.jsonl"
    assert second.name.startswith("session-")
    assert second.suffix == ".jsonl"
    assert second != first


def test_history_init_dry_run_discovers_sources_without_writes(tmp_path: Path):
    home = tmp_path / ".ai-memory"
    config = init_home(home)
    projects = tmp_path / ".claude" / "projects" / "demo"
    projects.mkdir(parents=True)
    session = projects / "session.jsonl"
    session.write_text('{"type":"user","message":"Use pytest"}\n', encoding="utf-8")
    store = SQLiteMemoryStore(config.store_path)
    store.initialize()
    queue = ReviewQueue(config.review_queue_path)

    summary = run_history_init(
        options=HistoryInitOptions(
            clients=("claude-code",),
            include_generic=(),
            review_only=True,
            auto_write_low_risk=False,
            limit=None,
            dry_run=True,
        ),
        config=config,
        source_home=tmp_path,
        store=store,
        queue=queue,
        extractor=None,
    )

    assert summary.clients_scanned == 1
    assert summary.sources_found == 1
    assert summary.sources_processed == 0
    assert summary.transcripts_archived == 0
    assert summary.extraction_skipped == 0
    assert not any((home / "raw").rglob("*.jsonl"))
    assert queue.list_pending() == []
    assert store.search("pytest", limit=10) == []


def test_history_init_archives_and_reports_missing_extractor(tmp_path: Path):
    home = tmp_path / ".ai-memory"
    config = init_home(home)
    transcript = tmp_path / "chat.md"
    transcript.write_text("User: Use pytest for tests", encoding="utf-8")
    store = SQLiteMemoryStore(config.store_path)
    store.initialize()
    queue = ReviewQueue(config.review_queue_path)

    summary = run_history_init(
        options=HistoryInitOptions(
            clients=(),
            include_generic=(transcript,),
            review_only=True,
            auto_write_low_risk=False,
            limit=None,
            dry_run=False,
        ),
        config=config,
        source_home=tmp_path,
        store=store,
        queue=queue,
        extractor=None,
    )

    assert summary.clients_scanned == 0
    assert summary.sources_found == 1
    assert summary.sources_processed == 1
    assert summary.transcripts_archived == 1
    assert summary.extraction_skipped == 1
    assert (home / "raw" / "generic" / "chat.md").read_text(encoding="utf-8") == "User: Use pytest for tests"
