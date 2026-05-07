from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from fastapi.testclient import TestClient

from ai_memory.server import server
from ai_memory.server.server import create_server


def test_first_registered_user_gets_admin_role_and_later_users_are_read(memory_home):
    memory_home.mkdir()
    server._jwt_secret = "test-secret"
    app = create_server(home=memory_home)
    client = TestClient(app)

    first_response = client.post(
        "/api/auth/register",
        params={"username": "admin", "password": "secret"},
    )
    second_response = client.post(
        "/api/auth/register",
        params={"username": "alice", "password": "secret"},
    )

    assert first_response.status_code == 201
    assert first_response.json()["user"]["role"] == "admin"
    assert second_response.status_code == 201
    assert second_response.json()["user"]["role"] == "read"


def test_concurrent_first_registration_creates_only_one_admin(memory_home, monkeypatch):
    memory_home.mkdir()
    server._jwt_secret = "test-secret"
    app = create_server(home=memory_home)
    barrier = Barrier(2)
    original_register_user = server.register_user

    def synchronized_register_user(*args, **kwargs):
        barrier.wait(timeout=5)
        return original_register_user(*args, **kwargs)

    monkeypatch.setattr(server, "register_user", synchronized_register_user)

    def register(username: str):
        return TestClient(app).post(
            "/api/auth/register",
            params={"username": username, "password": "secret"},
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(register, ["admin", "alice"]))

    assert [response.status_code for response in responses] == [201, 201]
    roles = [response.json()["user"]["role"] for response in responses]
    assert roles.count("admin") == 1
    assert roles.count("read") == 1
