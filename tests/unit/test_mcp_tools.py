from pathlib import Path

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
