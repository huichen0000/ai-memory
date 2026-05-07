from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from datetime import datetime, timezone

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
        owner_user_id: str | None = Query(None, description="Filter by owner user id"),
        limit: int = Query(50, ge=1, le=500, description="Maximum number of results"),
        offset: int = Query(0, ge=0, description="Number of results to skip"),
    ) -> JSONResponse:
        status_filter: tuple[str, ...] | None = None
        if status:
            status_filter = tuple(s.strip() for s in status.split(",") if s.strip())

        try:
            type_filter = type.strip() if type else None
            scope_filter = scope.strip() if scope else None
            owner_user_id_filter = owner_user_id.strip() if owner_user_id else None
            if q:
                memories = store.search(
                    q,
                    limit=limit,
                    offset=offset,
                    status_filter=status_filter,
                    type_filter=type_filter,
                    scope_filter=scope_filter,
                    owner_user_id_filter=owner_user_id_filter,
                )
                total = store.count_search(
                    q,
                    status_filter=status_filter,
                    type_filter=type_filter,
                    scope_filter=scope_filter,
                    owner_user_id_filter=owner_user_id_filter,
                )
            else:
                memories = store.list_page(
                    status_filter=status_filter,
                    type_filter=type_filter,
                    scope_filter=scope_filter,
                    owner_user_id_filter=owner_user_id_filter,
                    limit=limit,
                    offset=offset,
                )
                total = store.count_all(
                    status_filter=status_filter,
                    type_filter=type_filter,
                    scope_filter=scope_filter,
                    owner_user_id_filter=owner_user_id_filter,
                )

            memories_data = [_memory_to_dict(m) for m in memories]
            return JSONResponse({
                "memories": memories_data,
                "pagination": {
                    "limit": limit,
                    "offset": offset,
                    "total": total,
                    "has_next": offset + limit < total,
                    "has_previous": offset > 0,
                },
            })
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
        "owner_user_id": memory.owner_user_id,
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
        "owner_user_id": candidate.owner_user_id,
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
        return JSONResponse(store.get_stats())

    return router


def create_review_routes(queue: ReviewQueue, store: SQLiteMemoryStore) -> APIRouter:
    router = APIRouter(prefix="/api/review", tags=["review"])

    @router.get("")
    async def list_pending(
        limit: int = Query(50, ge=1, le=500, description="Maximum number of review items"),
        offset: int = Query(0, ge=0, description="Number of review items to skip"),
    ) -> JSONResponse:
        all_items = queue.list_pending()
        items = all_items[offset : offset + limit]
        total = len(all_items)
        return JSONResponse({
            "items": [_review_item_to_dict(item) for item in items],
            "pagination": {
                "limit": limit,
                "offset": offset,
                "total": total,
                "has_next": offset + limit < total,
                "has_previous": offset > 0,
            },
        })

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


def create_source_routes(raw_dir: Path) -> APIRouter:
    router = APIRouter(prefix="/api/sources", tags=["sources"])

    @router.get("")
    async def list_sources() -> JSONResponse:
        sources = []
        if not raw_dir.exists():
            return JSONResponse({"sources": sources})

        tz = timezone.utc
        for client_dir in sorted(raw_dir.iterdir()):
            if not client_dir.is_dir():
                continue
            client_name = client_dir.name
            for file_path in sorted(client_dir.iterdir()):
                if not file_path.is_file():
                    continue
                stat = file_path.stat()
                sources.append({
                    "name": file_path.name,
                    "client": client_name,
                    "path": f"{client_name}/{file_path.name}",
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime, tz=tz).isoformat(),
                })

        return JSONResponse({"sources": sources})

    @router.get("/{path:path}")
    async def get_source(path: str) -> JSONResponse:
        resolved_raw = raw_dir.resolve()
        file_path = (raw_dir / path).resolve()
        if not file_path.is_file() or not str(file_path).startswith(str(resolved_raw)):
            raise HTTPException(status_code=404, detail=f"Source not found: {path}")
        try:
            size = file_path.stat().st_size
            if size > 5 * 1024 * 1024:
                raise HTTPException(status_code=413, detail="File too large (max 5MB)")
            content = file_path.read_text(encoding="utf-8")
            return JSONResponse({"content": content})
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to read source: {e}")

    return router
