import sys
from pathlib import Path

import pytest

from ai_memory.adapters.generic_transcript import GenericTranscriptAdapter
from ai_memory.cli.main import run
from ai_memory.core.models import MemoryCandidate, NormalizedMessage, NormalizedTranscript
from ai_memory.extraction.providers.command import CommandExtractorProvider
from ai_memory.extraction.router import route_candidates
from ai_memory.extraction.validator import validate_candidate
from ai_memory.review.queue import ReviewQueue
from ai_memory.store.sqlite import SQLiteMemoryStore


def test_generic_markdown_transcript_normalizes_fixture():
    adapter = GenericTranscriptAdapter()
    transcript = adapter.normalize(Path("tests/fixtures/transcripts/generic/simple-chat.md"))

    assert transcript.client == "generic"
    assert transcript.messages[0].role == "user"
    assert "pytest" in transcript.messages[0].content


def test_validate_candidate_requires_valid_uri_and_evidence():
    candidate = MemoryCandidate(
        uri="project://local/demo/commands",
        type="project_command",
        scope="project",
        content="Use pytest for tests.",
        summary="Use pytest.",
        confidence=0.9,
        risk="low",
        evidence="user stated test command",
    )

    validate_candidate(candidate)


def test_validate_candidate_rejects_scope_uri_mismatch():
    candidate = MemoryCandidate(
        uri="project://local/demo/commands",
        type="project_command",
        scope="global",
        content="Use pytest for tests.",
        summary="Use pytest.",
        confidence=0.9,
        risk="low",
        evidence="user stated test command",
    )

    with pytest.raises(ValueError, match="scope does not match URI namespace"):
        validate_candidate(candidate)


def test_route_candidates_auto_writes_low_risk_and_queues_high_impact(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()
    queue = ReviewQueue(tmp_path / "review-queue.jsonl")
    low_risk = MemoryCandidate(
        uri="project://local/demo/commands",
        type="project_command",
        scope="project",
        content="Use pytest for tests.",
        summary="Use pytest.",
        confidence=0.9,
        risk="low",
        evidence="user stated test command",
    )
    high_impact = MemoryCandidate(
        uri="project://local/demo/testing",
        type="testing_rule",
        scope="project",
        content="All tests must use pytest.",
        summary="Testing rule uses pytest.",
        confidence=0.9,
        risk="low",
        evidence="user stated testing rule",
    )

    result = route_candidates([low_risk, high_impact], store, queue, auto_write_confidence=0.85)

    assert result == {"auto_approved": 1, "queued": 1, "discarded": 0}
    assert len(store.search("pytest", limit=10)) == 1
    assert len(queue.list_pending()) == 1


def test_route_candidates_queues_broad_scope_candidates(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()
    queue = ReviewQueue(tmp_path / "review-queue.jsonl")
    candidate = MemoryCandidate(
        uri="global://user/commands",
        type="project_command",
        scope="global",
        content="Use pytest for tests.",
        summary="Use pytest.",
        confidence=0.99,
        risk="low",
        evidence="user stated test command",
    )

    result = route_candidates([candidate], store, queue, auto_write_confidence=0.85)

    assert result == {"auto_approved": 0, "queued": 1, "discarded": 0}
    assert store.search("pytest", limit=10) == []
    assert len(queue.list_pending()) == 1


def test_route_candidates_deduplicates_auto_write_by_uri(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()
    queue = ReviewQueue(tmp_path / "review-queue.jsonl")
    candidate = make_candidate()

    first = route_candidates([candidate], store, queue, auto_write_confidence=0.85)
    second = route_candidates([candidate], store, queue, auto_write_confidence=0.85)

    assert first["auto_approved"] == 1
    assert second["auto_approved"] == 0
    assert len(store.search("pytest", limit=10)) == 1


def test_route_candidates_queues_conflicting_auto_write_uri(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()
    queue = ReviewQueue(tmp_path / "review-queue.jsonl")
    route_candidates([make_candidate()], store, queue, auto_write_confidence=0.85)
    conflict = replace_candidate(make_candidate(), content="Use unittest for tests.", summary="Use unittest.")

    result = route_candidates([conflict], store, queue, auto_write_confidence=0.85)

    assert result["auto_approved"] == 0
    assert result["queued"] == 1
    assert "conflicts with existing approved memory" in queue.list_pending()[0].reason


def test_command_provider_minimizes_transcript_payload(monkeypatch):
    captured = {}

    class Result:
        returncode = 0
        stdout = "[]"
        stderr = ""

    def fake_run(command, **kwargs):
        captured["payload"] = kwargs["input"]
        return Result()

    monkeypatch.setattr("ai_memory.extraction.providers.command.subprocess.run", fake_run)
    provider = CommandExtractorProvider([sys.executable, "-c", "print('[]')"])

    provider.extract(make_transcript())

    payload = captured["payload"]
    assert "tests/fixtures/transcripts/generic/simple-chat.md" not in payload
    assert '"source_name": "simple-chat.md"' in payload
    assert '"cwd"' not in payload
    assert '"session_id"' not in payload
    assert '"repo_id"' not in payload
    assert '"branch"' not in payload
    assert '"started_at"' not in payload
    assert '"ended_at"' not in payload


def test_command_provider_redacts_transcript_payload(monkeypatch, tmp_path: Path):
    captured = {}
    transcript_path = tmp_path / "chat.md"
    transcript = NormalizedTranscript(
        session_id="session-id",
        client="generic",
        source_path=str(transcript_path),
        messages=(NormalizedMessage(role="user", content="api_key=secret-value"),),
    )

    class Result:
        returncode = 0
        stdout = "[]"
        stderr = ""

    def fake_run(command, **kwargs):
        captured["payload"] = kwargs["input"]
        return Result()

    monkeypatch.setattr("ai_memory.extraction.providers.command.subprocess.run", fake_run)
    provider = CommandExtractorProvider([sys.executable, "-c", "print('[]')"])

    provider.extract(transcript)

    payload = captured["payload"]
    assert "secret-value" not in payload
    assert "[REDACTED:API_KEY]" in payload


def test_command_provider_raises_on_nonzero_exit():
    provider = CommandExtractorProvider([sys.executable, "-c", "import sys; print('bad', file=sys.stderr); sys.exit(2)"])

    with pytest.raises(RuntimeError, match="bad"):
        provider.extract(make_transcript())


def test_command_provider_raises_on_timeout():
    provider = CommandExtractorProvider([sys.executable, "-c", "import time; time.sleep(2)"], timeout_seconds=0.01)

    with pytest.raises(RuntimeError, match="timed out"):
        provider.extract(make_transcript())


def test_command_provider_rejects_invalid_json_and_non_list_output():
    invalid_json = CommandExtractorProvider([sys.executable, "-c", "print('not json')"])
    non_list = CommandExtractorProvider([sys.executable, "-c", "print('{}')"])

    with pytest.raises(ValueError, match="invalid JSON"):
        invalid_json.extract(make_transcript())
    with pytest.raises(ValueError, match="JSON list"):
        non_list.extract(make_transcript())


def test_command_provider_rejects_malformed_candidate_and_string_tags_or_triggers():
    missing_field = CommandExtractorProvider([sys.executable, "-c", "print('[{}]')"])
    string_tags = CommandExtractorProvider(
        [
            sys.executable,
            "-c",
            "import json; print(json.dumps([{"
            "'uri':'project://local/demo/commands','type':'project_command','scope':'project',"
            "'content':'Use pytest.','summary':'Use pytest.','confidence':0.9,'risk':'low',"
            "'evidence':'user stated command','tags':'testing'}]))",
        ]
    )
    string_triggers = CommandExtractorProvider(
        [
            sys.executable,
            "-c",
            "import json; print(json.dumps([{"
            "'uri':'project://local/demo/commands','type':'project_command','scope':'project',"
            "'content':'Use pytest.','summary':'Use pytest.','confidence':0.9,'risk':'low',"
            "'evidence':'user stated command','triggers':'pytest'}]))",
        ]
    )

    with pytest.raises(ValueError, match="missing required field"):
        missing_field.extract(make_transcript())
    with pytest.raises(ValueError, match="tags must be a list or tuple"):
        string_tags.extract(make_transcript())
    with pytest.raises(ValueError, match="triggers must be a list or tuple"):
        string_triggers.extract(make_transcript())


def test_validate_candidate_rejects_secrets_in_persisted_text_fields():
    fields = ("content", "summary", "evidence", "tags", "triggers")
    for field in fields:
        candidate = make_candidate()
        values = {field: "api_key=secret-value"}
        if field in {"tags", "triggers"}:
            values[field] = ("api_key=secret-value",)
        candidate = replace_candidate(candidate, **values)

        with pytest.raises(ValueError, match=field):
            validate_candidate(candidate)


def test_generic_transcript_falls_back_when_no_chat_lines(tmp_path: Path):
    transcript_path = tmp_path / "notes.md"
    transcript_path.write_text("Plain transcript text", encoding="utf-8")

    transcript = GenericTranscriptAdapter().normalize(transcript_path)

    assert transcript.messages[0].role == "transcript"
    assert transcript.messages[0].content == "Plain transcript text"


def test_generic_transcript_redacts_during_normalization(tmp_path: Path):
    transcript_path = tmp_path / "chat.md"
    transcript_path.write_text("User: api_key=secret-value", encoding="utf-8")

    transcript = GenericTranscriptAdapter().normalize(transcript_path)

    assert "secret-value" not in transcript.messages[0].content
    assert "[REDACTED:API_KEY]" in transcript.messages[0].content


def test_route_candidates_reports_sanitized_validation_errors(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()
    queue = ReviewQueue(tmp_path / "review-queue.jsonl")
    candidate = replace_candidate(make_candidate(), content="api_key=secret-value")

    result = route_candidates([candidate], store, queue, auto_write_confidence=0.85)

    assert result["discarded"] == 1
    assert result["errors"] == ["candidate content contains sensitive material"]
    assert "secret-value" not in result["errors"][0]


def make_transcript():
    return GenericTranscriptAdapter().normalize(Path("tests/fixtures/transcripts/generic/simple-chat.md"))


def make_candidate() -> MemoryCandidate:
    return MemoryCandidate(
        uri="project://local/demo/commands",
        type="project_command",
        scope="project",
        content="Use pytest for tests.",
        summary="Use pytest.",
        confidence=0.9,
        risk="low",
        evidence="user stated test command",
    )


def replace_candidate(candidate: MemoryCandidate, **changes: object) -> MemoryCandidate:
    data = candidate.__dict__ | changes
    return MemoryCandidate(**data)


def test_cli_import_generic_archive_only(tmp_path: Path, capsys):
    home = tmp_path / ".ai-memory"
    transcript = Path("tests/fixtures/transcripts/generic/simple-chat.md")
    run(["init", "--home", str(home)])

    assert run(["import", "--client", "generic", "--path", str(transcript), "--home", str(home), "--archive-only"]) == 0
    output = capsys.readouterr().out

    assert "Transcript archived" in output
    assert any((home / "raw" / "generic").iterdir())


def test_cli_import_rejects_without_archive_only(tmp_path: Path, capsys):
    home = tmp_path / ".ai-memory"
    transcript = Path("tests/fixtures/transcripts/generic/simple-chat.md")
    run(["init", "--home", str(home)])

    assert run(["import", "--client", "generic", "--path", str(transcript), "--home", str(home)]) == 2
    output = capsys.readouterr().out

    assert "--archive-only is required" in output
    assert not (home / "raw" / "generic" / transcript.name).exists()


def test_cli_import_rejects_duplicate_archive_name(tmp_path: Path, capsys):
    home = tmp_path / ".ai-memory"
    transcript = Path("tests/fixtures/transcripts/generic/simple-chat.md")
    run(["init", "--home", str(home)])

    assert run(["import", "--client", "generic", "--path", str(transcript), "--home", str(home), "--archive-only"]) == 0
    assert run(["import", "--client", "generic", "--path", str(transcript), "--home", str(home), "--archive-only"]) == 2
    output = capsys.readouterr().out

    assert "already exists" in output


def test_cli_import_rejects_missing_path(tmp_path: Path, capsys):
    home = tmp_path / ".ai-memory"
    missing = tmp_path / "missing.md"
    run(["init", "--home", str(home)])

    assert run(["import", "--client", "generic", "--path", str(missing), "--home", str(home), "--archive-only"]) == 2
    output = capsys.readouterr().out

    assert "Transcript path is not a file" in output


def test_cli_import_rejects_sensitive_path_without_override(tmp_path: Path, capsys):
    home = tmp_path / ".ai-memory"
    transcript = tmp_path / ".env"
    transcript.write_text("User: Remember to use pytest.", encoding="utf-8")
    run(["init", "--home", str(home)])

    assert run(["import", "--client", "generic", "--path", str(transcript), "--home", str(home), "--archive-only"]) == 2
    output = capsys.readouterr().out

    assert "Refusing to archive sensitive path" in output
    assert not (home / "raw" / "generic" / transcript.name).exists()


def test_cli_import_allows_sensitive_path_with_override(tmp_path: Path, capsys):
    home = tmp_path / ".ai-memory"
    transcript = tmp_path / ".env"
    transcript.write_text("User: Remember to use pytest.", encoding="utf-8")
    run(["init", "--home", str(home)])

    assert (
        run([
            "import",
            "--client",
            "generic",
            "--path",
            str(transcript),
            "--home",
            str(home),
            "--archive-only",
            "--allow-sensitive-source",
        ])
        == 0
    )
    output = capsys.readouterr().out

    assert "Transcript archived" in output
    assert (home / "raw" / "generic" / transcript.name).exists()


def test_cli_import_rejects_sensitive_symlink_target_without_override(tmp_path: Path, capsys):
    home = tmp_path / ".ai-memory"
    target = tmp_path / ".env"
    target.write_text("User: Remember to use pytest.", encoding="utf-8")
    transcript = tmp_path / "chat.md"
    transcript.symlink_to(target)
    run(["init", "--home", str(home)])

    assert run(["import", "--client", "generic", "--path", str(transcript), "--home", str(home), "--archive-only"]) == 2
    output = capsys.readouterr().out

    assert "Refusing to archive sensitive path" in output
    assert not (home / "raw" / "generic" / transcript.name).exists()


def test_cli_import_rejects_non_utf8_input(tmp_path: Path, capsys):
    home = tmp_path / ".ai-memory"
    transcript = tmp_path / "binary.md"
    transcript.write_bytes(b"\xff\xfe\xfd")
    run(["init", "--home", str(home)])

    assert run(["import", "--client", "generic", "--path", str(transcript), "--home", str(home), "--archive-only"]) == 2
    output = capsys.readouterr().out

    assert "Transcript must be UTF-8 text" in output
    assert not (home / "raw" / "generic" / transcript.name).exists()


def test_cli_import_rejects_unsupported_client(tmp_path: Path, capsys):
    home = tmp_path / ".ai-memory"
    transcript = Path("tests/fixtures/transcripts/generic/simple-chat.md")
    run(["init", "--home", str(home)])

    assert run(["import", "--client", "claude-code", "--path", str(transcript), "--home", str(home), "--archive-only"]) == 2
    output = capsys.readouterr().out

    assert "Only generic import is supported" in output
