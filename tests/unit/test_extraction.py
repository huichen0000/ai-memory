from pathlib import Path

from ai_memory.adapters.generic_transcript import GenericTranscriptAdapter
from ai_memory.core.models import MemoryCandidate
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
