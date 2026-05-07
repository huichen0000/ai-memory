import sys
from pathlib import Path
from socket import timeout as SocketTimeout
from urllib.error import HTTPError

import pytest
import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ai_memory.auth.users import create_user, init_auth_db
from ai_memory.cli.main import run as cli_run
from ai_memory.core.config import config_to_dict, init_home
from ai_memory.core.models import MemoryCandidate
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
from ai_memory.server.history_import import MAX_IMPORT_SOURCE_BYTES
from ai_memory.store.sqlite import SQLiteMemoryStore


class FakeAdapter:
    def __init__(self, paths: list[Path]):
        self.paths = paths

    def discover(self) -> list[Path]:
        return self.paths


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


def test_history_options_require_explicit_routing_mode():
    with pytest.raises(ValueError, match="either --review-only or --auto-write-low-risk is required"):
        HistoryInitOptions(
            clients=("claude-code",),
            include_generic=(),
            review_only=False,
            auto_write_low_risk=False,
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


def test_archive_target_for_skips_existing_stable_suffix_targets(tmp_path: Path):
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
    second.write_text("archived", encoding="utf-8")

    third = archive_target_for(raw_dir, HistorySource("claude-code", source_b))

    assert third != first
    assert third != second
    assert not third.exists()
    assert third.name == f"{second.stem}-2{second.suffix}"


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


def test_history_init_rejects_sensitive_include_generic_without_override(tmp_path: Path):
    home = tmp_path / ".ai-memory"
    config = init_home(home)
    transcript = tmp_path / "credentials.json"
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

    assert summary.sources_found == 1
    assert summary.sources_processed == 0
    assert summary.transcripts_archived == 0
    assert summary.transcripts_skipped == 1
    assert "Refusing to archive sensitive path" in summary.errors[0]
    assert not (home / "raw" / "generic" / transcript.name).exists()


def test_history_init_allows_sensitive_include_generic_with_override(tmp_path: Path):
    home = tmp_path / ".ai-memory"
    config = init_home(home)
    transcript = tmp_path / "credentials.json"
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
            allow_sensitive_source=True,
        ),
        config=config,
        source_home=tmp_path,
        store=store,
        queue=queue,
        extractor=None,
    )

    assert summary.sources_processed == 1
    assert summary.transcripts_archived == 1
    assert (home / "raw" / "generic" / transcript.name).exists()


def test_history_init_sensitive_override_does_not_apply_to_discovered_clients(tmp_path: Path, monkeypatch):
    home = tmp_path / ".ai-memory"
    config = init_home(home)
    transcript = tmp_path / "credentials.json"
    transcript.write_text("User: Use pytest for tests", encoding="utf-8")
    store = SQLiteMemoryStore(config.store_path)
    store.initialize()
    queue = ReviewQueue(config.review_queue_path)
    monkeypatch.setattr("ai_memory.history.initializer._adapter_for", lambda client, home: FakeAdapter([transcript]))

    summary = run_history_init(
        options=HistoryInitOptions(
            clients=("claude-code",),
            include_generic=(),
            review_only=True,
            auto_write_low_risk=False,
            limit=None,
            dry_run=False,
            allow_sensitive_source=True,
        ),
        config=config,
        source_home=tmp_path,
        store=store,
        queue=queue,
        extractor=None,
    )

    assert summary.sources_found == 1
    assert summary.sources_processed == 0
    assert summary.transcripts_archived == 0
    assert summary.transcripts_skipped == 1
    assert "Refusing to archive sensitive path" in summary.errors[0]


def test_history_init_rejects_sensitive_symlink_target_without_override(tmp_path: Path):
    home = tmp_path / ".ai-memory"
    config = init_home(home)
    target = tmp_path / ".env"
    target.write_text("User: Use pytest for tests", encoding="utf-8")
    transcript = tmp_path / "chat.md"
    transcript.symlink_to(target)
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

    assert summary.sources_found == 1
    assert summary.sources_processed == 0
    assert summary.transcripts_archived == 0
    assert summary.transcripts_skipped == 1
    assert "Refusing to archive sensitive path" in summary.errors[0]
    assert not (home / "raw" / "generic" / transcript.name).exists()


def test_history_init_dry_run_reports_sensitive_source_skip(tmp_path: Path):
    home = tmp_path / ".ai-memory"
    config = init_home(home)
    transcript = tmp_path / "credentials.json"
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
            dry_run=True,
        ),
        config=config,
        source_home=tmp_path,
        store=store,
        queue=queue,
        extractor=None,
    )

    assert summary.sources_found == 1
    assert summary.sources_processed == 0
    assert summary.transcripts_archived == 0
    assert summary.transcripts_skipped == 1
    assert "Refusing to archive sensitive path" in summary.errors[0]


class StaticExtractor:
    def __init__(self, candidates: list[MemoryCandidate]):
        self.candidates = candidates

    def extract(self, transcript):
        return self.candidates


class FailingExtractor:
    def extract(self, transcript):
        raise ValueError("bad extractor output")


def low_risk_candidate() -> MemoryCandidate:
    return MemoryCandidate(
        uri="project://local/demo/commands",
        type="project_command",
        scope="project",
        content="Use pytest for tests.",
        summary="Use pytest.",
        confidence=0.9,
        risk="low",
        evidence="historical transcript stated test command",
    )


def high_impact_candidate() -> MemoryCandidate:
    return MemoryCandidate(
        uri="project://local/demo/testing",
        type="testing_rule",
        scope="project",
        content="All tests must use pytest.",
        summary="Tests use pytest.",
        confidence=0.9,
        risk="low",
        evidence="historical transcript stated testing rule",
    )


def test_history_init_review_only_queues_low_risk_candidate(tmp_path: Path):
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
        extractor=StaticExtractor([low_risk_candidate()]),
    )

    assert summary.candidates_extracted == 1
    assert summary.review_queued == 1
    assert summary.auto_written == 0
    assert len(queue.list_pending()) == 1
    assert store.search("pytest", limit=10) == []
    assert "historical import from generic requires review" in queue.list_pending()[0].reason


def test_history_init_records_extractor_error_and_continues(tmp_path: Path):
    home = tmp_path / ".ai-memory"
    config = init_home(home)
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"
    first.write_text("User: one", encoding="utf-8")
    second.write_text("User: two", encoding="utf-8")
    store = SQLiteMemoryStore(config.store_path)
    store.initialize()
    queue = ReviewQueue(config.review_queue_path)

    summary = run_history_init(
        options=HistoryInitOptions(
            clients=(),
            include_generic=(first, second),
            review_only=True,
            auto_write_low_risk=False,
            limit=None,
            dry_run=False,
        ),
        config=config,
        source_home=tmp_path,
        store=store,
        queue=queue,
        extractor=FailingExtractor(),
    )

    assert summary.sources_processed == 2
    assert summary.transcripts_archived == 2
    assert summary.candidates_extracted == 0
    assert len(summary.errors) == 2
    assert all("bad extractor output" in error for error in summary.errors)


def test_history_init_auto_write_binds_records_to_owner_user_id(tmp_path: Path):
    home = tmp_path / ".ai-memory"
    config = init_home(home)
    transcript = tmp_path / "chat.md"
    transcript.write_text("User: Use pytest", encoding="utf-8")
    store = SQLiteMemoryStore(config.store_path)
    store.initialize()
    queue = ReviewQueue(config.review_queue_path)

    summary = run_history_init(
        options=HistoryInitOptions(
            clients=(),
            include_generic=(transcript,),
            review_only=False,
            auto_write_low_risk=True,
            limit=None,
            dry_run=False,
            owner_user_id="user_admin",
        ),
        config=config,
        source_home=tmp_path,
        store=store,
        queue=queue,
        extractor=StaticExtractor([low_risk_candidate()]),
    )

    records = store.search("pytest", limit=10)
    assert summary.auto_written == 1
    assert len(records) == 1
    assert records[0].owner_user_id == "user_admin"


def test_history_init_auto_write_low_risk_uses_existing_policy(tmp_path: Path):
    home = tmp_path / ".ai-memory"
    config = init_home(home)
    transcript = tmp_path / "chat.md"
    transcript.write_text("User: Use pytest", encoding="utf-8")
    store = SQLiteMemoryStore(config.store_path)
    store.initialize()
    queue = ReviewQueue(config.review_queue_path)

    summary = run_history_init(
        options=HistoryInitOptions(
            clients=(),
            include_generic=(transcript,),
            review_only=False,
            auto_write_low_risk=True,
            limit=None,
            dry_run=False,
        ),
        config=config,
        source_home=tmp_path,
        store=store,
        queue=queue,
        extractor=StaticExtractor([low_risk_candidate(), high_impact_candidate()]),
    )

    assert summary.candidates_extracted == 2
    assert summary.auto_written == 1
    assert summary.review_queued == 1
    assert summary.discarded == 0
    assert len(store.search("pytest", limit=10)) == 1
    pending = queue.list_pending()
    assert len(pending) == 1
    assert pending[0].candidate.type == "testing_rule"


def test_history_init_auto_write_queues_conflicting_uri(tmp_path: Path):
    home = tmp_path / ".ai-memory"
    config = init_home(home)
    transcript = tmp_path / "chat.md"
    transcript.write_text("User: Use pytest", encoding="utf-8")
    store = SQLiteMemoryStore(config.store_path)
    store.initialize()
    queue = ReviewQueue(config.review_queue_path)
    store.create_memory(low_risk_candidate(), status="auto_approved", change_reason="existing")
    conflict = MemoryCandidate(
        uri=low_risk_candidate().uri,
        type="project_command",
        scope="project",
        content="Use unittest for tests.",
        summary="Use unittest.",
        confidence=0.9,
        risk="low",
        evidence="historical transcript stated test command",
    )

    summary = run_history_init(
        options=HistoryInitOptions(
            clients=(),
            include_generic=(transcript,),
            review_only=False,
            auto_write_low_risk=True,
            limit=None,
            dry_run=False,
        ),
        config=config,
        source_home=tmp_path,
        store=store,
        queue=queue,
        extractor=StaticExtractor([conflict]),
    )

    assert summary.auto_written == 0
    assert summary.review_queued == 1
    assert "conflicts with existing approved memory" in queue.list_pending()[0].reason


def test_cli_history_init_dry_run_outputs_summary(tmp_path: Path, capsys):
    home = tmp_path / ".ai-memory"
    source_home = tmp_path / "source-home"
    projects = source_home / ".claude" / "projects" / "demo"
    projects.mkdir(parents=True)
    (projects / "session.jsonl").write_text('{"type":"user","message":"Use pytest"}\n', encoding="utf-8")

    result = cli_run([
        "history",
        "init",
        "--home",
        str(home),
        "--source-home",
        str(source_home),
        "--clients",
        "claude-code",
        "--dry-run",
    ])

    output = capsys.readouterr().out
    assert result == 0
    assert "Historical initialization complete." in output
    assert "Clients scanned: 1" in output
    assert "Sources found: 1" in output
    assert "Dry run only. No archives, review items, or memories were written." in output
    assert not home.exists()


def test_cli_history_init_uses_configured_command_extractor(tmp_path: Path, capsys):
    home = tmp_path / ".ai-memory"
    config = init_home(home)
    config_data = config_to_dict(config)
    config_data["extractor"] = {
        "provider": "command",
        "command": (
            f'"{sys.executable}" -c '
            '"import json; print(json.dumps([{'
            "'uri': 'project://local/demo/history', "
            "'type': 'project_command', "
            "'scope': 'project', "
            "'content': 'Use pytest for tests.', "
            "'summary': 'Use pytest.', "
            "'confidence': 0.9, "
            "'risk': 'low', "
            "'evidence': 'historical transcript', "
            "'tags': ['pytest'], "
            "'triggers': ['pytest']"
            '}]))"'
        ),
        "max_input_chars": config.max_input_chars,
    }
    (home / "config.yaml").write_text(yaml.safe_dump(config_data, sort_keys=False), encoding="utf-8")
    transcript = tmp_path / "chat.md"
    transcript.write_text("User: Use pytest for tests", encoding="utf-8")

    result = cli_run([
        "history",
        "init",
        "--home",
        str(home),
        "--source-home",
        str(tmp_path),
        "--clients",
        "claude-code",
        "--include-generic",
        str(transcript),
        "--review-only",
    ])

    output = capsys.readouterr().out
    pending = ReviewQueue(home / "review-queue.jsonl").list_pending()

    assert result == 0
    assert "Candidates extracted: 1" in output
    assert "Review queued: 1" in output
    assert len(pending) == 1


def test_cli_history_init_auto_write_binds_owner_username(tmp_path: Path, capsys):
    home = tmp_path / ".ai-memory"
    config = init_home(home)
    auth_db = home / "auth.db"
    init_auth_db(auth_db)
    engine = create_engine(f"sqlite:///{auth_db}")
    with Session(engine) as db:
        user = create_user(db, "admin", "secret", role="admin")
    config_data = config_to_dict(config)
    config_data["extractor"] = {
        "provider": "command",
        "command": [
            sys.executable,
            "-c",
            (
                "import json; "
                "print(json.dumps([{"
                "'uri': 'project://local/demo/owner', "
                "'type': 'project_command', "
                "'scope': 'project', "
                "'content': 'Use pytest for tests.', "
                "'summary': 'Use pytest.', "
                "'confidence': 0.9, "
                "'risk': 'low', "
                "'evidence': 'historical transcript'"
                "}]))"
            ),
        ],
        "max_input_chars": config.max_input_chars,
    }
    (home / "config.yaml").write_text(yaml.safe_dump(config_data, sort_keys=False), encoding="utf-8")
    transcript = tmp_path / "chat.md"
    transcript.write_text("User: Use pytest for tests", encoding="utf-8")

    result = cli_run([
        "history",
        "init",
        "--home",
        str(home),
        "--source-home",
        str(tmp_path),
        "--clients",
        "claude-code",
        "--include-generic",
        str(transcript),
        "--auto-write-low-risk",
        "--owner-username",
        "admin",
    ])

    output = capsys.readouterr().out
    records = SQLiteMemoryStore(config.store_path).search("pytest", limit=10)

    assert result == 0
    assert "Auto-written: 1" in output
    assert len(records) == 1
    assert records[0].owner_user_id == user.id


def test_cli_history_init_auto_write_defaults_to_admin_owner(tmp_path: Path, capsys):
    home = tmp_path / ".ai-memory"
    config = init_home(home)
    auth_db = home / "auth.db"
    init_auth_db(auth_db)
    engine = create_engine(f"sqlite:///{auth_db}")
    with Session(engine) as db:
        user = create_user(db, "admin", "secret", role="admin")
    config_data = config_to_dict(config)
    config_data["extractor"] = {
        "provider": "command",
        "command": [
            sys.executable,
            "-c",
            (
                "import json; "
                "print(json.dumps([{"
                "'uri': 'project://local/demo/default-owner', "
                "'type': 'project_command', "
                "'scope': 'project', "
                "'content': 'Use pytest default owner.', "
                "'summary': 'Use pytest.', "
                "'confidence': 0.9, "
                "'risk': 'low', "
                "'evidence': 'historical transcript'"
                "}]))"
            ),
        ],
        "max_input_chars": config.max_input_chars,
    }
    (home / "config.yaml").write_text(yaml.safe_dump(config_data, sort_keys=False), encoding="utf-8")
    transcript = tmp_path / "chat.md"
    transcript.write_text("User: Use pytest", encoding="utf-8")

    result = cli_run([
        "history",
        "init",
        "--home",
        str(home),
        "--source-home",
        str(tmp_path),
        "--clients",
        "claude-code",
        "--include-generic",
        str(transcript),
        "--auto-write-low-risk",
    ])

    records = SQLiteMemoryStore(config.store_path).search("pytest", limit=10)

    assert result == 0
    assert len(records) == 1
    assert records[0].owner_user_id == user.id


def test_cli_history_push_discovers_local_sources_and_uploads_to_server(tmp_path: Path, monkeypatch, capsys):
    source_home = tmp_path / "source-home"
    projects = source_home / ".claude" / "projects" / "demo"
    projects.mkdir(parents=True)
    transcript = projects / "session.jsonl"
    transcript.write_text('{"type":"user","message":"Use pytest remotely"}\n', encoding="utf-8")
    requests: list[tuple[str, dict, dict[str, str]]] = []

    def fake_post_json(url: str, payload: dict, headers: dict[str, str], timeout: float = 60) -> dict:
        requests.append((url, payload, headers))
        if url.endswith("/api/history/import-sessions"):
            return {"session_id": "hist_sess_test"}
        if url.endswith("/api/history/import-sessions/hist_sess_test/sources"):
            return {"status": "uploaded"}
        if url.endswith("/api/history/import-sessions/hist_sess_test/process"):
            return {"summary": {"sources_found": 1, "auto_written": 1}}
        raise HTTPError(url, 404, "not found", hdrs=None, fp=None)

    monkeypatch.setattr("ai_memory.cli.main._post_json", fake_post_json)

    result = cli_run([
        "history",
        "push",
        "--server",
        "https://memory.example.com/",
        "--api-key",
        "test-key",
        "--source-home",
        str(source_home),
        "--clients",
        "claude-code",
        "--auto-write-low-risk",
        "--redact-archive",
    ])

    output = capsys.readouterr().out
    assert result == 0
    assert "Sources uploaded: 1" in output
    assert requests[0] == (
        "https://memory.example.com/api/history/import-sessions",
        {"clients": ["claude-code"], "redact_archive": True},
        {"Authorization": "Bearer test-key"},
    )
    assert requests[1][1]["client"] == "claude-code"
    assert requests[1][1]["name"] == "session.jsonl"
    assert "Use pytest remotely" in requests[1][1]["content"]
    assert requests[2][1] == {"auto_write_low_risk": True, "review_only": False}


def test_cli_history_push_uses_longer_timeout_for_processing(tmp_path: Path, monkeypatch, capsys):
    source_home = tmp_path / "source-home"
    projects = source_home / ".claude" / "projects" / "demo"
    projects.mkdir(parents=True)
    (projects / "session.jsonl").write_text('{"type":"user","message":"Use pytest remotely"}\n', encoding="utf-8")
    timeouts: list[tuple[str, float]] = []

    def fake_post_json(url: str, payload: dict, headers: dict[str, str], timeout: float = 60) -> dict:
        timeouts.append((url, timeout))
        if url.endswith("/api/history/import-sessions"):
            return {"session_id": "hist_sess_test"}
        if url.endswith("/api/history/import-sessions/hist_sess_test/sources"):
            return {"status": "uploaded"}
        if url.endswith("/api/history/import-sessions/hist_sess_test/process"):
            return {"summary": {"sources_found": 1, "auto_written": 1}}
        raise HTTPError(url, 404, "not found", hdrs=None, fp=None)

    monkeypatch.setattr("ai_memory.cli.main._post_json", fake_post_json)

    result = cli_run([
        "history",
        "push",
        "--server",
        "https://memory.example.com",
        "--api-key",
        "test-key",
        "--source-home",
        str(source_home),
        "--clients",
        "claude-code",
        "--auto-write-low-risk",
    ])

    assert result == 0
    assert timeouts[-1][0].endswith("/process")
    assert timeouts[-1][1] > 60


def test_cli_history_push_process_timeout_prints_status_without_traceback(tmp_path: Path, monkeypatch, capsys):
    source_home = tmp_path / "source-home"
    projects = source_home / ".claude" / "projects" / "demo"
    projects.mkdir(parents=True)
    (projects / "session.jsonl").write_text('{"type":"user","message":"Use pytest remotely"}\n', encoding="utf-8")

    def fake_post_json(url: str, payload: dict, headers: dict[str, str], timeout: float = 60) -> dict:
        if url.endswith("/api/history/import-sessions"):
            return {"session_id": "hist_sess_test"}
        if url.endswith("/api/history/import-sessions/hist_sess_test/sources"):
            return {"status": "uploaded"}
        if url.endswith("/api/history/import-sessions/hist_sess_test/process"):
            raise SocketTimeout("timed out")
        raise HTTPError(url, 404, "not found", hdrs=None, fp=None)

    monkeypatch.setattr("ai_memory.cli.main._post_json", fake_post_json)

    result = cli_run([
        "history",
        "push",
        "--server",
        "https://memory.example.com",
        "--api-key",
        "test-key",
        "--source-home",
        str(source_home),
        "--clients",
        "claude-code",
        "--auto-write-low-risk",
    ])

    output = capsys.readouterr().out
    assert result == 0
    assert "Sources uploaded: 1" in output
    assert "Processing request timed out" in output
    assert "hist_sess_test" in output


def test_cli_history_push_skips_sources_larger_than_server_limit(tmp_path: Path, monkeypatch, capsys):
    source_home = tmp_path / "source-home"
    projects = source_home / ".claude" / "projects" / "demo"
    projects.mkdir(parents=True)
    (projects / "large.jsonl").write_text("x" * (MAX_IMPORT_SOURCE_BYTES + 1), encoding="utf-8")
    uploaded_payloads: list[dict] = []

    def fake_post_json(url: str, payload: dict, headers: dict[str, str], timeout: float = 60) -> dict:
        if url.endswith("/api/history/import-sessions"):
            return {"session_id": "hist_sess_test"}
        if url.endswith("/api/history/import-sessions/hist_sess_test/sources"):
            uploaded_payloads.append(payload)
            return {"status": "uploaded"}
        if url.endswith("/api/history/import-sessions/hist_sess_test/process"):
            return {"summary": {"sources_found": 0, "auto_written": 0}}
        raise HTTPError(url, 404, "not found", hdrs=None, fp=None)

    monkeypatch.setattr("ai_memory.cli.main._post_json", fake_post_json)

    result = cli_run([
        "history",
        "push",
        "--server",
        "https://memory.example.com",
        "--api-key",
        "test-key",
        "--source-home",
        str(source_home),
        "--clients",
        "claude-code",
        "--auto-write-low-risk",
    ])

    output = capsys.readouterr().out
    assert result == 0
    assert "Sources uploaded: 0" in output
    assert uploaded_payloads == []


def test_cli_history_init_rejects_invalid_client(tmp_path: Path, capsys):
    result = cli_run(["history", "init", "--home", str(tmp_path / ".ai-memory"), "--clients", "unknown"])

    output = capsys.readouterr().err
    assert result == 2
    assert "Unsupported history client: unknown" in output


def test_cli_history_init_rejects_conflicting_modes(tmp_path: Path, capsys):
    result = cli_run([
        "history",
        "init",
        "--home",
        str(tmp_path / ".ai-memory"),
        "--review-only",
        "--auto-write-low-risk",
    ])

    output = capsys.readouterr().err
    assert result == 2
    assert "mutually exclusive" in output
