from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp

from ai_memory.auth.jwt_ import create_token, verify_token
from ai_memory.auth.users import (
    AuthUser,
    create_user,
    delete_user,
    init_auth_db,
    list_users,
    regenerate_api_key,
    verify_api_key,
    verify_credentials,
)
from ai_memory.retrieval.environment import detect_environment
from ai_memory.review.queue import ReviewQueue
from ai_memory.store.sqlite import SQLiteMemoryStore


_jwt_secret: str | None = None


def _get_jwt_secret() -> str:
    global _jwt_secret
    if _jwt_secret is None:
        config_path = Path.home() / ".ai-memory" / ".auth_secret"
        if config_path.exists():
            _jwt_secret = config_path.read_text().strip()
        else:
            _jwt_secret = secrets.token_urlsafe(32)
            config_path.write_text(_jwt_secret)
    return _jwt_secret


def _require_auth(
    x_api_key: str | None = None,
    authorization: str | None = None,
    auth_db_path: Path | None = None,
) -> AuthUser | None:
    """Authenticate via API key or JWT. Returns None if no credentials provided."""
    key = x_api_key or (authorization.removeprefix("Bearer ").removeprefix("bearer ") if authorization else "")

    if not key:
        return None

    # Try API key first
    if auth_db_path and auth_db_path.exists():
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        engine = create_engine(f"sqlite:///{auth_db_path}")
        with Session(engine) as db:
            user = verify_api_key(db, key)
            if user:
                return user

    # Try JWT
    secret = _get_jwt_secret()
    payload = verify_token(key, secret)
    if payload:
        return AuthUser(id=payload["sub"], username=payload["username"], api_key="", role=payload.get("role", "read"))

    return None


def _require_write(
    x_api_key: str | None = None,
    authorization: str | None = None,
    auth_db_path: Path | None = None,
) -> AuthUser:
    user = _require_auth(x_api_key, authorization, auth_db_path)
    if not user:
        raise HTTPException(status_code=401, detail="Missing authentication")
    if user.role not in ("write", "admin"):
        raise HTTPException(status_code=403, detail="Write permission required")
    return user


def create_server(home: Path | None = None) -> FastAPI:
    memory_home = home or Path.home() / ".ai-memory"
    auth_db_path = memory_home / "auth.db"

    # Ensure auth DB exists
    if not auth_db_path.exists():
        init_auth_db(auth_db_path)

    app = FastAPI(title="ai-memory Server")

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Auth endpoints ---

    @app.post("/api/auth/login")
    def login(username: str, password: str) -> JSONResponse:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        engine = create_engine(f"sqlite:///{auth_db_path}")
        with Session(engine) as db:
            user = verify_credentials(db, username, password)
            if not user:
                raise HTTPException(status_code=401, detail="Invalid credentials")
            token = create_token(user.id, user.username, _get_jwt_secret(), role=user.role)
            return JSONResponse({
                "token": token,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "role": user.role,
                    "api_key": user.api_key,
                },
            })

    @app.post("/api/auth/register")
    def register(username: str, password: str) -> JSONResponse:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        engine = create_engine(f"sqlite:///{auth_db_path}")
        with Session(engine) as db:
            try:
                user = create_user(db, username, password, role="read")
                token = create_token(user.id, user.username, _get_jwt_secret(), role=user.role)
                return JSONResponse({
                    "token": token,
                    "user": {
                        "id": user.id,
                        "username": user.username,
                        "role": user.role,
                        "api_key": user.api_key,
                    },
                }, status_code=201)
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))

    @app.get("/api/auth/me")
    def me(
        x_api_key: str | None = Header(None),
        authorization: str | None = Header(None),
    ) -> JSONResponse:
        user = _require_auth(x_api_key, authorization, auth_db_path)
        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated")
        return JSONResponse({
            "id": user.id,
            "username": user.username,
            "role": user.role,
        })

    @app.get("/api/admin/users")
    def admin_list_users(
        x_api_key: str | None = Header(None),
        authorization: str | None = Header(None),
    ) -> JSONResponse:
        user = _require_auth(x_api_key, authorization, auth_db_path)
        if not user or user.role != "admin":
            raise HTTPException(status_code=403, detail="Admin required")
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        engine = create_engine(f"sqlite:///{auth_db_path}")
        with Session(engine) as db:
            return JSONResponse({"users": list_users(db)})

    @app.delete("/api/admin/users/{user_id}")
    def admin_delete_user(
        user_id: str,
        x_api_key: str | None = Header(None),
        authorization: str | None = Header(None),
    ) -> JSONResponse:
        user = _require_auth(x_api_key, authorization, auth_db_path)
        if not user or user.role != "admin":
            raise HTTPException(status_code=403, detail="Admin required")
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        engine = create_engine(f"sqlite:///{auth_db_path}")
        with Session(engine) as db:
            ok = delete_user(db, user_id)
            if not ok:
                raise HTTPException(status_code=404, detail="User not found")
            return JSONResponse({"status": "deleted"})

    @app.post("/api/admin/users/{user_id}/regenerate-key")
    def admin_regenerate_key(
        user_id: str,
        x_api_key: str | None = Header(None),
        authorization: str | None = Header(None),
    ) -> JSONResponse:
        user = _require_auth(x_api_key, authorization, auth_db_path)
        if not user or user.role != "admin":
            raise HTTPException(status_code=403, detail="Admin required")
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        engine = create_engine(f"sqlite:///{auth_db_path}")
        with Session(engine) as db:
            key = regenerate_api_key(db, user_id)
            if not key:
                raise HTTPException(status_code=404, detail="User not found")
            return JSONResponse({"api_key": key})

    @app.post("/api/admin/users")
    def admin_create_user(
        username: str,
        password: str,
        role: str = "read",
        x_api_key: str | None = Header(None),
        authorization: str | None = Header(None),
    ) -> JSONResponse:
        user = _require_auth(x_api_key, authorization, auth_db_path)
        if not user or user.role != "admin":
            raise HTTPException(status_code=403, detail="Admin required")
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        engine = create_engine(f"sqlite:///{auth_db_path}")
        with Session(engine) as db:
            try:
                new_user = create_user(db, username, password, role=role)
                return JSONResponse({
                    "id": new_user.id,
                    "username": new_user.username,
                    "role": new_user.role,
                    "api_key": new_user.api_key,
                }, status_code=201)
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))

    # --- Mount MCP with auth middleware ---
    from mcp.server.fastmcp import FastMCP

    store = SQLiteMemoryStore(memory_home / "memory.db")
    store.initialize()
    queue = ReviewQueue(memory_home / "review-queue.jsonl")
    workspace = Path.cwd().resolve()

    def trusted_env(prompt: str) -> dict[str, str | None]:
        return detect_environment(workspace, client="mcp", prompt=prompt)

    mcp = FastMCP("ai-memory")

    @mcp.tool()
    def memory_search_tool(query: str, limit: int = 10) -> dict:
        from ai_memory.retrieval.assembler import assemble_context
        results = store.search(query, limit)
        filtered = [r for r in results if r.status in ("approved", "auto_approved")]
        return assemble_context(filtered, query, trusted_env(query))

    @mcp.tool()
    def memory_context_tool(prompt: str, max_items: int = 12) -> dict:
        from ai_memory.retrieval.assembler import assemble_context
        results = store.search(prompt, max_items)
        filtered = [r for r in results if r.status in ("approved", "auto_approved")]
        return assemble_context(filtered, prompt, trusted_env(prompt))

    @mcp.tool()
    def memory_read_tool(memory_id: str) -> dict:
        record = store.get_memory(memory_id)
        if not record:
            return {"error": f"Memory not found: {memory_id}"}
        return {
            "id": record.id,
            "uri": record.uri,
            "type": record.type,
            "scope": record.scope,
            "content": record.content,
            "summary": record.summary,
            "status": record.status,
        }

    @mcp.tool()
    def memory_write_tool(payload: dict) -> dict:
        from ai_memory.mcp.tools import memory_write
        return memory_write(store, queue, payload, trusted_env("memory write"), review_only=False)

    # Wrap MCP ASGI app with auth middleware
    mcp_app = mcp.streamable_http_app

    class AuthMiddleware:
        def __init__(self, app: ASGIApp):
            self.app = app

        async def __call__(self, scope, receive, send):
            # MCP uses POST to /mcp with JSON-RPC
            if scope["type"] == "http" and scope.get("path", "").startswith("/mcp"):
                # Check auth
                headers = dict(scope.get("headers", []))
                api_key = headers.get(b"x-api-key", b"").decode() or None
                auth_header = headers.get(b"authorization", b"").decode() or None
                user = _require_auth(api_key, auth_header, auth_db_path)
                if not user:
                    from starlette.responses import JSONResponse
                    response = JSONResponse({"error": "Unauthorized"}, status_code=401)
                    await response(scope, receive, send)
                    return
            await self.app(scope, receive, send)

    app.mount("/mcp", AuthMiddleware(mcp_app))

    # --- Mount existing web dashboard at / ---
    from ai_memory.web.dashboard import create_app as create_web_app
    web_app = create_web_app(home=memory_home)
    app.mount("/", web_app)

    return app


def run_server(host: str = "0.0.0.0", port: int = 8080, home: Path | None = None) -> None:
    import uvicorn
    app = create_server(home)
    uvicorn.run(app, host=host, port=port)
