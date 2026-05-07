from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_memory.core.models import MemoryCandidate
from ai_memory.review.queue import ReviewQueue
from ai_memory.store.sqlite import SQLiteMemoryStore
from ai_memory.web.routes import create_review_routes


def make_candidate(index: int) -> MemoryCandidate:
    return MemoryCandidate(
        uri=f"project://local/demo/review-{index}",
        type="project_command",
        scope="project",
        content=f"Review candidate {index}",
        summary=f"Review {index}",
        confidence=0.7,
        risk="medium",
        evidence="test fixture",
        tags=("review",),
        triggers=("review",),
        repo_id="local/demo",
    )


def test_review_list_returns_requested_page_and_pagination_metadata(memory_home):
    queue = ReviewQueue(memory_home / "review-queue.jsonl")
    store = SQLiteMemoryStore(memory_home / "memory.db")
    store.initialize()
    for index in range(5):
        queue.enqueue(make_candidate(index), reason="needs review")

    app = FastAPI()
    app.include_router(create_review_routes(queue, store))

    response = TestClient(app).get("/api/review?limit=2&offset=2")

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["pagination"] == {
        "limit": 2,
        "offset": 2,
        "total": 5,
        "has_next": True,
        "has_previous": True,
    }
