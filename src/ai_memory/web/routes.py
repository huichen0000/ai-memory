from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from ai_memory.store.sqlite import SQLiteMemoryStore


def create_memory_store(home: Path) -> SQLiteMemoryStore:
    store = SQLiteMemoryStore(home / "memory.db")
    store.initialize()
    return store


def create_memory_routes(store: SQLiteMemoryStore) -> APIRouter:
    router = APIRouter(prefix="/api/memories", tags=["memories"])

    @router.get("")
    async def list_memories(
        status: str | None = Query(None, description="Comma-separated status values"),
        type: str | None = Query(None, description="Filter by memory type"),
        scope: str | None = Query(None, description="Filter by scope"),
        q: str | None = Query(None, description="Search query"),
        limit: int = Query(50, ge=1, le=500, description="Maximum number of results"),
    ) -> JSONResponse:
        status_filter: tuple[str, ...] | None = None
        if status:
            status_filter = tuple(s.strip() for s in status.split(",") if s.strip())

        try:
            if q:
                memories = store.search(q, limit)
                if status_filter:
                    memories = [m for m in memories if m.status in status_filter]
            else:
                memories = store.list_all(status_filter=status_filter)

            if type_filter := (type.strip() if type else None):
                memories = [m for m in memories if m.type == type_filter]
            if scope_filter := (scope.strip() if scope else None):
                memories = [m for m in memories if m.scope == scope_filter]

            memories = memories[:limit]

            memories_data = [_memory_to_dict(m) for m in memories]
            return JSONResponse({"memories": memories_data})
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/{memory_id}")
    async def get_memory(memory_id: str) -> JSONResponse:
        memory = store.get_memory(memory_id)
        if memory is None:
            raise HTTPException(status_code=404, detail=f"Memory not found: {memory_id}")
        return JSONResponse({"memory": _memory_to_dict(memory)})

    @router.put("/{memory_id}")
    async def update_memory(memory_id: str, request: dict) -> JSONResponse:
        content = request.get("content")
        if content is None:
            raise HTTPException(status_code=400, detail="content is required")
        memory = store.get_memory(memory_id)
        if memory is None:
            raise HTTPException(status_code=404, detail=f"Memory not found: {memory_id}")
        reason = request.get("reason", "Updated via web editor")
        updated = store.update_memory(memory_id, content, reason)
        return JSONResponse({"memory": _memory_to_dict(updated)})

    return router


def _memory_to_dict(memory: Any) -> dict[str, Any]:
    return {
        "id": memory.id,
        "uri": memory.uri,
        "type": memory.type,
        "scope": memory.scope,
        "content": memory.content,
        "summary": memory.summary,
        "status": memory.status,
        "confidence": memory.confidence,
        "risk": memory.risk,
        "repo_id": memory.repo_id,
        "branch": memory.branch,
        "path_glob": memory.path_glob,
        "expires_at": memory.expires_at,
        "created_at": memory.created_at,
        "updated_at": memory.updated_at,
        "triggers": list(memory.triggers) if memory.triggers else [],
    }
