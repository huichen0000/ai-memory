from pathlib import Path
from typing import Any

from ai_memory.core.models import MemoryCandidate
from ai_memory.mcp.tools import memory_context, memory_read, memory_search, memory_write
from ai_memory.review.queue import ReviewQueue
from ai_memory.store.sqlite import SQLiteMemoryStore


def test_memory_write_without_trusted_environment_is_review_only(tmp_path: Path):
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
            "repo_id": "local/demo",
        },
    )

    assert write_result["status"] == "queued"
    assert len(queue.list_pending()) == 1
    search_result = memory_search(
        store=store,
        query="pytest",
        limit=5,
        environment={"repo_id": "local/demo", "branch": None, "relative_path": None},
    )
    assert search_result["items"] == []


def test_memory_search_requires_environment(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()
    store.create_memory(
        MemoryCandidate(
            uri="project://other/repo/commands",
            type="project_command",
            scope="project",
            content="Use pytest for tests.",
            summary="Use pytest.",
            confidence=0.9,
            risk="low",
            evidence="test",
            repo_id="other/repo",
        ),
        status="auto_approved",
        change_reason="test",
    )

    result = memory_search(store=store, query="pytest", limit=5)

    assert result == {"items": [], "error": "environment is required for scoped retrieval"}


def test_memory_context_requires_environment(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()
    store.create_memory(
        MemoryCandidate(
            uri="project://other/repo/commands",
            type="project_command",
            scope="project",
            content="Use pytest for tests.",
            summary="Use pytest.",
            confidence=0.9,
            risk="low",
            evidence="test",
            repo_id="other/repo",
        ),
        status="auto_approved",
        change_reason="test",
    )

    result = memory_context(store=store, prompt="pytest", max_items=5)

    assert result["items"] == []
    assert result["error"] == "environment is required for scoped retrieval"


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
            repo_id="local/demo",
        ),
        status="auto_approved",
        change_reason="test",
    )

    environment = {"repo_id": "local/demo", "branch": None, "relative_path": None}
    context = memory_context(store=store, prompt="pytest", max_items=5, environment=environment)
    assert "Use pytest for tests." in context["context"]

    read_result = memory_read(store=store, memory_id=record.id, environment=environment)
    assert read_result["item"]["id"] == record.id


def test_memory_read_excludes_unapproved_records(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()
    record = store.create_memory(
        MemoryCandidate(
            uri="project://local/demo/proposed",
            type="project_command",
            scope="project",
            content="Proposed pytest memory.",
            summary="Proposed pytest.",
            confidence=0.9,
            risk="low",
            evidence="test",
            repo_id="local/demo",
        ),
        status="proposed",
        change_reason="test",
    )

    result = memory_read(
        store=store,
        memory_id=record.id,
        environment={"repo_id": "local/demo", "branch": None, "relative_path": None},
    )

    assert result == {"item": None}


def test_memory_write_rejects_trusted_environment_uri_mismatch(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()
    queue = ReviewQueue(tmp_path / "review-queue.jsonl")

    result = memory_write(
        store=store,
        queue=queue,
        payload=payload(uri="project://other/repo/commands", repo_id="other/repo"),
        trusted_environment={"repo_id": "local/demo", "branch": "main", "relative_path": None},
    )

    assert result["status"] == "discarded"
    assert store.search("pytest", limit=10) == []


def test_memory_write_binds_repo_to_trusted_environment(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()
    queue = ReviewQueue(tmp_path / "review-queue.jsonl")

    result = memory_write(
        store=store,
        queue=queue,
        payload=payload(uri="project://local/demo/commands", repo_id="other/repo"),
        trusted_environment={"repo_id": "local/demo", "branch": "main", "relative_path": None},
    )

    assert result["status"] == "auto_approved"
    records = store.search("pytest", limit=10)
    assert records[0].repo_id == "local/demo"


def test_memory_write_rejects_scope_uri_mismatch_with_trusted_environment(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()
    queue = ReviewQueue(tmp_path / "review-queue.jsonl")

    result = memory_write(
        store=store,
        queue=queue,
        payload=payload(uri="project://local/demo/commands", scope="global", repo_id="local/demo"),
        trusted_environment={"repo_id": "local/demo", "branch": "main", "relative_path": None},
    )

    assert result["status"] == "discarded"
    assert store.search("pytest", limit=10) == []


def test_memory_write_queues_global_scope_with_trusted_environment(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()
    queue = ReviewQueue(tmp_path / "review-queue.jsonl")

    result = memory_write(
        store=store,
        queue=queue,
        payload=payload(uri="global://user/commands", scope="global"),
        trusted_environment={"repo_id": "local/demo", "branch": "main", "relative_path": None},
    )

    assert result["status"] == "queued"
    assert store.search("pytest", limit=10) == []
    assert len(queue.list_pending()) == 1


def test_memory_write_review_only_with_trusted_environment_queues_project_candidate(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()
    queue = ReviewQueue(tmp_path / "review-queue.jsonl")

    result = memory_write(
        store=store,
        queue=queue,
        payload=payload(uri="project://local/demo/commands", repo_id="other/repo"),
        trusted_environment={"repo_id": "local/demo", "branch": "main", "relative_path": None},
        review_only=True,
    )

    assert result["status"] == "queued"
    assert store.search("pytest", limit=10) == []
    assert len(queue.list_pending()) == 1


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


def test_memory_read_blocks_forged_repo_environment_when_trusted_environment_is_supplied(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()
    record = store.create_memory(
        MemoryCandidate(
            uri="project://other/repo/commands",
            type="project_command",
            scope="project",
            content="Use pytest for tests.",
            summary="Use pytest.",
            confidence=0.9,
            risk="low",
            evidence="test",
            repo_id="other/repo",
        ),
        status="auto_approved",
        change_reason="test",
    )

    result = memory_read(
        store=store,
        memory_id=record.id,
        environment={"repo_id": "other/repo", "branch": None, "relative_path": None},
        trusted_environment={"repo_id": "local/demo", "branch": None, "relative_path": None},
    )

    assert result == {"item": None}


def test_memory_read_requires_environment(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()

    assert memory_read(store=store, memory_id="mem_missing") == {
        "item": None,
        "error": "environment is required for scoped retrieval",
    }


def test_memory_read_missing_id_returns_none(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()

    assert memory_read(
        store=store,
        memory_id="mem_missing",
        environment={"repo_id": "local/demo", "branch": None, "relative_path": None},
    ) == {"item": None}


def test_search_ranks_after_collecting_all_token_matches(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()
    for index in range(55):
        store.create_memory(
            MemoryCandidate(
                uri=f"project://local/demo/pytest/{index}",
                type="project_command",
                scope="project",
                content=f"Use pytest command {index}.",
                summary="Use pytest.",
                confidence=0.99,
                risk="low",
                evidence="test",
                tags=("pytest",),
                triggers=("pytest",),
                repo_id="local/demo",
            ),
            status="auto_approved",
            change_reason="test",
        )
    marker = store.create_memory(
        MemoryCandidate(
            uri="branch://local/demo/main/marker",
            type="project_command",
            scope="branch",
            content="Use marker command.",
            summary="Use marker.",
            confidence=0.7,
            risk="low",
            evidence="test",
            tags=("marker",),
            triggers=("marker",),
            repo_id="local/demo",
            branch="main",
        ),
        status="auto_approved",
        change_reason="test",
    )

    result = memory_search(
        store=store,
        query="pytest marker",
        limit=1,
        environment={"repo_id": "local/demo", "branch": "main", "relative_path": None},
    )

    assert result["items"][0]["id"] == marker.id


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
            repo_id="local/demo",
        ),
        status="auto_approved",
        change_reason="test",
    )

    environment = {"repo_id": "local/demo", "branch": None, "relative_path": None}
    search = memory_search(store=store, query='repo:("pytest"?)', limit=5, environment=environment)
    context = memory_context(store=store, prompt='run "pytest -k unit"?', max_items=5, environment=environment)

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
                repo_id="local/demo",
            ),
            status="auto_approved",
            change_reason="test",
        )

    environment = {"repo_id": "local/demo", "branch": None, "relative_path": None}
    negative_search = memory_search(store=store, query="pytest", limit=-1, environment=environment)
    oversized_search = memory_search(store=store, query="pytest", limit=1000, environment=environment)
    negative_context = memory_context(store=store, prompt="pytest", max_items=-1, environment=environment)
    oversized_context = memory_context(store=store, prompt="pytest", max_items=1000, environment=environment)

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
