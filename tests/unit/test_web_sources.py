from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_memory.web.routes import create_source_routes


def test_sources_list_returns_file_metadata(memory_home):
    raw_dir = memory_home / "raw"
    source_dir = raw_dir / "claude-code"
    source_dir.mkdir(parents=True)
    source_file = source_dir / "session.jsonl"
    source_file.write_text('{"message":"hello"}\n', encoding="utf-8")

    app = FastAPI()
    app.include_router(create_source_routes(raw_dir))

    response = TestClient(app).get("/api/sources")

    assert response.status_code == 200
    assert response.json()["sources"] == [
        {
            "name": "session.jsonl",
            "client": "claude-code",
            "path": "claude-code/session.jsonl",
            "size": source_file.stat().st_size,
            "modified": response.json()["sources"][0]["modified"],
        }
    ]
    assert response.json()["sources"][0]["modified"].endswith("+00:00")
