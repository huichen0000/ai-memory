from pathlib import Path
from typing import Any

from ai_memory.core.models import MemoryCandidate
from ai_memory.mcp.tools import memory_context, memory_read, memory_search, memory_write
from ai_memory.review.queue import ReviewQueue
from ai_memory.store.sqlite import SQLiteMemoryStore


def test_memory_write_and_search(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()
    queue = ReviewQueue(tmp_path / "review-queue.jsonl")

    write_result = memory_write(
        store=store,
        queue=queue,
        payload={
            "uri": "project://local/demo/commands",
            "type": "project_command",
            "scope": "project",
            "content": "Use pytest for tests.",
            "summary": "Use pytest.",
            "confidence": 0.9,
            "risk": "low",
            "evidence": "manual MCP write",
        },
    )

    assert write_result["status"] == "auto_approved"
    search_result = memory_search(store=store, query="pytest", limit=5)
    assert search_result["items"][0]["content"] == "Use pytest for tests."


def test_memory_context_and_read(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()
    record = store.create_memory(
        MemoryCandidate(
            uri="project://local/demo/commands",
            type="project_command",
            scope="project",
            content="Use pytest for tests.",
            summary="Use pytest.",
            confidence=0.9,
            risk="low",
            evidence="test",
            tags=("pytest",),
            triggers=("pytest",),
        ),
        status="auto_approved",
        change_reason="test",
    )

    context = memory_context(store=store, prompt="pytest", max_items=5)
    assert "Use pytest for tests." in context["context"]

    read_result = memory_read(store=store, memory_id=record.id)
    assert read_result["item"]["id"] == record.id


def test_high_impact_write_returns_queued(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()
    queue = ReviewQueue(tmp_path / "review-queue.jsonl")

    result = memory_write(store=store, queue=queue, payload=payload(type="testing_rule"))

    assert result["status"] == "queued"
    assert len(queue.list_pending()) == 1


def test_low_confidence_write_returns_discarded(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()
    queue = ReviewQueue(tmp_path / "review-queue.jsonl")

    result = memory_write(store=store, queue=queue, payload=payload(confidence=0.1))

    assert result["status"] == "discarded"
    assert queue.list_pending() == []


def test_malformed_writes_return_controlled_discarded_response(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()
    queue = ReviewQueue(tmp_path / "review-queue.jsonl")

    malformed_payloads: list[Any] = [
        None,
        {"content": "missing required fields"},
        payload(tags=None),
        payload(tags="abc"),
        payload(tags=("pytest", 123)),
        payload(triggers=None),
        payload(triggers="pytest"),
        payload(triggers=("pytest", object())),
        payload(content="api_key=secret-value"),
    ]

    for malformed in malformed_payloads:
        result = memory_write(store=store, queue=queue, payload=malformed)
        assert result["status"] == "discarded"
        assert "secret-value" not in result.get("error", "")


def test_memory_read_missing_id_returns_none(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()

    assert memory_read(store=store, memory_id="mem_missing") == {"item": None}


def test_punctuation_heavy_queries_find_matches_without_fts_errors(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()
    store.create_memory(
        MemoryCandidate(
            uri="project://local/demo/commands",
            type="project_command",
            scope="project",
            content="Use pytest for tests.",
            summary="Use pytest.",
            confidence=0.9,
            risk="low",
            evidence="test",
            tags=("pytest",),
            triggers=("pytest",),
        ),
        status="auto_approved",
        change_reason="test",
    )

    search = memory_search(store=store, query='repo:("pytest"?)', limit=5)
    context = memory_context(store=store, prompt='run "pytest -k unit"?', max_items=5)

    assert search["items"][0]["content"] == "Use pytest for tests."
    assert "Use pytest for tests." in context["context"]


def test_negative_and_oversized_limits_are_clamped(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()
    for index in range(55):
        store.create_memory(
            MemoryCandidate(
                uri=f"project://local/demo/commands/{index}",
                type="project_command",
                scope="project",
                content=f"Use pytest command {index}.",
                summary="Use pytest.",
                confidence=0.9,
                risk="low",
                evidence="test",
                tags=("pytest",),
                triggers=("pytest",),
            ),
            status="auto_approved",
            change_reason="test",
        )

    negative_search = memory_search(store=store, query="pytest", limit=-1)
    oversized_search = memory_search(store=store, query="pytest", limit=1000)
    negative_context = memory_context(store=store, prompt="pytest", max_items=-1)
    oversized_context = memory_context(store=store, prompt="pytest", max_items=1000)

    assert len(negative_search["items"]) == 1
    assert len(oversized_search["items"]) == 50
    assert len(negative_context["items"]) == 1
    assert len(oversized_context["items"]) == 50


def payload(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "uri": "project://local/demo/commands",
        "type": "project_command",
        "scope": "project",
        "content": "Use pytest for tests.",
        "summary": "Use pytest.",
        "confidence": 0.9,
        "risk": "low",
        "evidence": "manual MCP write",
    }
    data.update(overrides)
    return data
