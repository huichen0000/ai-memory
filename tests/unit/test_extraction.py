import sys
from pathlib import Path

import pytest

from ai_memory.adapters.generic_transcript import GenericTranscriptAdapter
from ai_memory.core.models import MemoryCandidate
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
