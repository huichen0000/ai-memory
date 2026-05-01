from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from ai_memory.core.models import MemoryCandidate
from ai_memory.extraction.validator import validate_candidate
from ai_memory.review.queue import ReviewQueue
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


def _candidate_to_dict(candidate: MemoryCandidate) -> dict[str, Any]:
    return {
        "uri": candidate.uri,
        "type": candidate.type,
        "scope": candidate.scope,
        "content": candidate.content,
        "summary": candidate.summary,
        "confidence": candidate.confidence,
        "risk": candidate.risk,
        "evidence": candidate.evidence,
        "tags": list(candidate.tags) if candidate.tags else [],
        "triggers": list(candidate.triggers) if candidate.triggers else [],
        "repo_id": candidate.repo_id,
        "branch": candidate.branch,
        "path_glob": candidate.path_glob,
        "expires_at": candidate.expires_at,
        "source_client": candidate.source_client,
        "session_id": candidate.session_id,
        "transcript_ref": candidate.transcript_ref,
    }


def _review_item_to_dict(item: Any) -> dict[str, Any]:
    return {
        "id": item.id,
        "candidate": _candidate_to_dict(item.candidate),
        "reason": item.reason,
        "status": item.status,
        "created_at": item.created_at,
        "reviewed_at": item.reviewed_at,
    }


def create_stats_routes(store: SQLiteMemoryStore) -> APIRouter:
    router = APIRouter(prefix="/api/stats", tags=["stats"])

    @router.get("")
    async def get_stats() -> JSONResponse:
        memories = store.list_all()
        total = len(memories)

        by_status: dict[str, int] = {}
        by_type: dict[str, int] = {}
        by_scope: dict[str, int] = {}

        for m in memories:
            by_status[m.status] = by_status.get(m.status, 0) + 1
            by_type[m.type] = by_type.get(m.type, 0) + 1
            by_scope[m.scope] = by_scope.get(m.scope, 0) + 1

        return JSONResponse({
            "total": total,
            "by_status": by_status,
            "by_type": by_type,
            "by_scope": by_scope,
        })

    return router


def create_review_routes(queue: ReviewQueue, store: SQLiteMemoryStore) -> APIRouter:
    router = APIRouter(prefix="/api/review", tags=["review"])

    @router.get("")
    async def list_pending() -> JSONResponse:
        items = queue.list_pending()
        return JSONResponse({"items": [_review_item_to_dict(item) for item in items]})

    @router.post("/{review_id}/approve")
    async def approve_item(review_id: str) -> JSONResponse:
        try:
            item = queue.get_pending(review_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

        try:
            validate_candidate(item.candidate)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Validation failed: {e}")

        existing = store.get_by_uri(item.candidate.uri)

        if existing is None:
            store.create_memory(item.candidate, "approved", f"Approved from review: {item.reason}")
        elif existing.content == item.candidate.content:
            store.append_source(existing.id, item.candidate)
        else:
            raise HTTPException(
                status_code=409,
                detail="Conflicting memory already exists for this URI with different content",
            )

        queue.mark(review_id, "approved")
        return JSONResponse({"status": "approved"})

    @router.post("/{review_id}/reject")
    async def reject_item(review_id: str) -> JSONResponse:
        try:
            queue.get_pending(review_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

        queue.mark(review_id, "rejected")
        return JSONResponse({"status": "rejected"})

    return router
