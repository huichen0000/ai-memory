from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_memory.core.models import MemoryCandidate
from ai_memory.store.sqlite import SQLiteMemoryStore
from ai_memory.web.routes import create_memory_routes


def make_candidate(index: int, *, status_word: str = "approved", owner_user_id: str | None = None) -> MemoryCandidate:
    return MemoryCandidate(
        uri=f"project://local/demo/memory-{index}",
        type="project_command",
        scope="project",
        content=f"Memory {index} content {status_word}",
        summary=f"Memory {index}",
        confidence=0.91,
        risk="low",
        evidence="test fixture",
        tags=("pagination", status_word),
        triggers=("pagination", status_word),
        repo_id="local/demo",
        owner_user_id=owner_user_id,
    )


def test_memories_list_returns_requested_page_and_pagination_metadata(memory_home):
    store = SQLiteMemoryStore(memory_home / "memory.db")
    store.initialize()
    for index in range(5):
        store.create_memory(make_candidate(index), status="approved", change_reason="test insert")

    app = FastAPI()
    app.include_router(create_memory_routes(store))

    response = TestClient(app).get("/api/memories?limit=2&offset=2")

    assert response.status_code == 200
    data = response.json()
    assert len(data["memories"]) == 2
    assert data["pagination"] == {
        "limit": 2,
        "offset": 2,
        "total": 5,
        "has_next": True,
        "has_previous": True,
    }


def test_memories_search_falls_back_to_content_substring_matches(memory_home):
    store = SQLiteMemoryStore(memory_home / "memory.db")
    store.initialize()
    record = store.create_memory(make_candidate(0, status_word="setup"), status="approved", change_reason="test insert")
    with store.connect() as db:
        db.execute("DELETE FROM memory_fts WHERE memory_id = ?", (record.id,))

    app = FastAPI()
    app.include_router(create_memory_routes(store))

    response = TestClient(app).get("/api/memories?q=setup&limit=50&offset=0")

    assert response.status_code == 200
    data = response.json()
    assert [memory["id"] for memory in data["memories"]] == [record.id]
    assert data["pagination"]["total"] == 1


def test_memories_search_next_page_returns_remaining_results(memory_home):
    store = SQLiteMemoryStore(memory_home / "memory.db")
    store.initialize()
    for index in range(51):
        store.create_memory(make_candidate(index, status_word="admin"), status="approved", change_reason="test insert")

    app = FastAPI()
    app.include_router(create_memory_routes(store))

    response = TestClient(app).get("/api/memories?q=admin&limit=50&offset=50")

    assert response.status_code == 200
    data = response.json()
    assert len(data["memories"]) == 1
    assert data["pagination"] == {
        "limit": 50,
        "offset": 50,
        "total": 51,
        "has_next": False,
        "has_previous": True,
    }


def test_memories_search_supports_offset_pagination(memory_home):
    store = SQLiteMemoryStore(memory_home / "memory.db")
    store.initialize()
    created = [
        store.create_memory(make_candidate(index, status_word="needle"), status="approved", change_reason="test insert")
        for index in range(5)
    ]
    with store.connect() as db:
        for index, record in enumerate(created):
            db.execute("UPDATE memories SET updated_at = ? WHERE id = ?", (f"2026-01-01T00:00:0{index}+00:00", record.id))

    app = FastAPI()
    app.include_router(create_memory_routes(store))

    response = TestClient(app).get("/api/memories?q=needle&limit=2&offset=2")

    assert response.status_code == 200
    data = response.json()
    assert [memory["id"] for memory in data["memories"]] == [created[2].id, created[1].id]
    assert data["pagination"] == {
        "limit": 2,
        "offset": 2,
        "total": 5,
        "has_next": True,
        "has_previous": True,
    }


def test_memories_list_filters_by_owner_user_id(memory_home):
    store = SQLiteMemoryStore(memory_home / "memory.db")
    store.initialize()
    admin_record = store.create_memory(
        make_candidate(0, owner_user_id="user_admin"),
        status="auto_approved",
        change_reason="test insert",
    )
    store.create_memory(
        make_candidate(1, owner_user_id="user_other"),
        status="auto_approved",
        change_reason="test insert",
    )

    app = FastAPI()
    app.include_router(create_memory_routes(store))

    response = TestClient(app).get("/api/memories?status=auto_approved&owner_user_id=user_admin&limit=50&offset=0")

    assert response.status_code == 200
    data = response.json()
    assert [memory["id"] for memory in data["memories"]] == [admin_record.id]
    assert data["pagination"]["total"] == 1


def test_memories_search_filters_by_owner_user_id(memory_home):
    store = SQLiteMemoryStore(memory_home / "memory.db")
    store.initialize()
    admin_record = store.create_memory(
        make_candidate(0, status_word="needle", owner_user_id="user_admin"),
        status="auto_approved",
        change_reason="test insert",
    )
    store.create_memory(
        make_candidate(1, status_word="needle", owner_user_id="user_other"),
        status="auto_approved",
        change_reason="test insert",
    )

    app = FastAPI()
    app.include_router(create_memory_routes(store))

    response = TestClient(app).get("/api/memories?status=auto_approved&q=needle&owner_user_id=user_admin&limit=50&offset=0")

    assert response.status_code == 200
    data = response.json()
    assert [memory["id"] for memory in data["memories"]] == [admin_record.id]
    assert data["pagination"]["total"] == 1
