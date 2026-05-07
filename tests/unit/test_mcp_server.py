from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from ai_memory.auth.users import create_user, init_auth_db
from ai_memory.server.server import create_server


def test_cli_mcp_serve_ignores_blank_stdio_lines(tmp_path: Path):
    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["USERPROFILE"] = str(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from ai_memory.cli.main import run; raise SystemExit(run(['mcp', 'serve']))",
        ],
        input="\n",
        text=True,
        capture_output=True,
        timeout=5,
        env=env,
    )

    assert result.returncode == 0
    assert "Internal Server Error" not in result.stdout
    assert "Invalid JSON" not in result.stderr


def test_combined_server_exposes_mcp_at_configured_path(tmp_path: Path):
    home = tmp_path / "memory"
    home.mkdir()
    init_auth_db(home / "auth.db")
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine(f"sqlite:///{home / 'auth.db'}")
    with Session(engine) as db:
        user = create_user(db, "writer", "secret", role="write")

    with TestClient(create_server(home=home)) as client:
        response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            headers={"X-API-Key": user.api_key},
        )

    assert response.status_code != 404
