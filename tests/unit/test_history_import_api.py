from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from ai_memory.core.config import config_to_dict, init_home
from ai_memory.server import server
from ai_memory.server.server import create_server
from ai_memory.review.queue import ReviewQueue
from ai_memory.server.history_import import MAX_IMPORT_SOURCE_BYTES
from ai_memory.store.sqlite import SQLiteMemoryStore


def _write_test_extractor(home: Path) -> None:
    config = init_home(home)
    data = config_to_dict(config)
    data["extractor"] = {
        "provider": "command",
        "command": [
            sys.executable,
            "-c",
            (
                "import json, sys; "
                "payload=json.load(sys.stdin); "
                "text=' '.join(m.get('content','') for m in payload.get('messages', [])); "
                "print(json.dumps([{'uri':'project://local/imported/remote-history',"
                "'type':'project_command','scope':'project','content':text,'summary':text[:80],"
                "'confidence':0.95,'risk':'low','evidence':'remote history import',"
                "'tags':['remote-history'],'triggers':['pytest'],'repo_id':'local/imported'}]))"
            ),
        ],
    }
    (home / "config.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_history_import_session_uploads_processes_and_binds_to_authenticated_user(memory_home):
    memory_home.mkdir()
    _write_test_extractor(memory_home)
    server._jwt_secret = "test-secret"
    client = TestClient(create_server(home=memory_home))
    register_response = client.post("/api/auth/register", params={"username": "admin", "password": "secret"})
    token = register_response.json()["token"]
    user_id = register_response.json()["user"]["id"]
    headers = {"Authorization": f"Bearer {token}"}

    session_response = client.post(
        "/api/history/import-sessions",
        json={"clients": ["claude-code"], "redact_archive": True, "owner_user_id": "attacker"},
        headers=headers,
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    upload_response = client.post(
        f"/api/history/import-sessions/{session_id}/sources",
        json={
            "client": "claude-code",
            "path": "projects/demo/session.jsonl",
            "name": "session.jsonl",
            "content": '{"type":"user","message":"Use pytest for remote imports"}\n',
            "owner_user_id": "attacker",
        },
        headers=headers,
    )
    assert upload_response.status_code == 201

    process_response = client.post(
        f"/api/history/import-sessions/{session_id}/process",
        json={"auto_write_low_risk": True, "review_only": False, "owner_user_id": "attacker"},
        headers=headers,
    )

    assert process_response.status_code == 200
    summary = process_response.json()["summary"]
    assert summary["sources_found"] == 1
    assert summary["auto_written"] == 1
    records = SQLiteMemoryStore(memory_home / "memory.db").search("pytest", limit=10)
    assert len(records) == 1
    assert records[0].owner_user_id == user_id


def test_history_import_review_candidate_exposes_authenticated_owner(memory_home):
    memory_home.mkdir()
    _write_test_extractor(memory_home)
    server._jwt_secret = "test-secret"
    client = TestClient(create_server(home=memory_home))
    register_response = client.post("/api/auth/register", params={"username": "admin", "password": "secret"})
    token = register_response.json()["token"]
    user_id = register_response.json()["user"]["id"]
    headers = {"Authorization": f"Bearer {token}"}
    session_id = client.post(
        "/api/history/import-sessions",
        json={"clients": ["claude-code"]},
        headers=headers,
    ).json()["session_id"]
    client.post(
        f"/api/history/import-sessions/{session_id}/sources",
        json={
            "client": "claude-code",
            "path": "projects/demo/session.jsonl",
            "name": "session.jsonl",
            "content": '{"type":"user","message":"Use pytest review imports"}\n',
        },
        headers=headers,
    )

    response = client.post(
        f"/api/history/import-sessions/{session_id}/process",
        json={"review_only": True, "auto_write_low_risk": False},
        headers=headers,
    )

    assert response.status_code == 200
    item = ReviewQueue(memory_home / "review-queue.jsonl").list_pending()[0]
    assert item.candidate.owner_user_id == user_id
    review_response = client.get("/api/review", headers=headers)
    assert review_response.json()["items"][0]["candidate"]["owner_user_id"] == user_id


def test_history_import_rejects_oversized_source(memory_home):
    memory_home.mkdir()
    server._jwt_secret = "test-secret"
    client = TestClient(create_server(home=memory_home))
    register_response = client.post("/api/auth/register", params={"username": "admin", "password": "secret"})
    headers = {"Authorization": f"Bearer {register_response.json()['token']}"}
    session_id = client.post(
        "/api/history/import-sessions",
        json={"clients": ["claude-code"]},
        headers=headers,
    ).json()["session_id"]

    response = client.post(
        f"/api/history/import-sessions/{session_id}/sources",
        json={
            "client": "claude-code",
            "name": "large.jsonl",
            "content": "x" * (MAX_IMPORT_SOURCE_BYTES + 1),
        },
        headers=headers,
    )

    assert response.status_code == 400


def test_history_import_session_requires_write_auth(memory_home):
    memory_home.mkdir()
    server._jwt_secret = "test-secret"
    client = TestClient(create_server(home=memory_home))

    response = client.post("/api/history/import-sessions", json={"clients": ["claude-code"]})

    assert response.status_code == 401
