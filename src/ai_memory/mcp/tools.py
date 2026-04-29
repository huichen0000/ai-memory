from __future__ import annotations

import re
import sqlite3
from dataclasses import asdict
from typing import Any

from ai_memory.core.models import MemoryCandidate
from ai_memory.extraction.router import route_candidates
from ai_memory.retrieval.assembler import assemble_context
from ai_memory.retrieval.ranking import rank_records
from ai_memory.review.queue import ReviewQueue
from ai_memory.store.sqlite import SQLiteMemoryStore


def _tokenize(value: str) -> tuple[str, ...]:
    seen: list[str] = []
    for token in re.findall(r"[a-z0-9_-]+", value.lower()):
        if token not in seen:
            seen.append(token)
    return tuple(seen)


def _safe_search(store: SQLiteMemoryStore, query: str, limit: int) -> list[Any]:
    if not query.strip():
        return []
    tokens = _tokenize(query)
    if not tokens:
        return []
    seen: set[str] = set()
    records = []
    for token in tokens:
        try:
            matches = store.search(token, limit)
        except sqlite3.OperationalError:
            continue
        for record in matches:
            if record.id not in seen:
                seen.add(record.id)
                records.append(record)
    return records[:limit]


def memory_search(store: SQLiteMemoryStore, query: str, limit: int = 10) -> dict[str, Any]:
    records = _safe_search(store, query, limit)
    return {"items": [asdict(record) for record in records]}


def memory_context(store: SQLiteMemoryStore, prompt: str, max_items: int = 12) -> dict[str, Any]:
    records = rank_records(_safe_search(store, prompt, max_items))[:max_items]
    return {"context": assemble_context(records), "items": [asdict(record) for record in records]}


def memory_read(store: SQLiteMemoryStore, memory_id: str) -> dict[str, Any]:
    record = store.get_memory(memory_id)
    if record is None:
        return {"item": None}
    return {"item": asdict(record)}


def memory_write(store: SQLiteMemoryStore, queue: ReviewQueue, payload: dict[str, Any]) -> dict[str, Any]:
    candidate_payload = dict(payload)
    candidate_payload["tags"] = tuple(candidate_payload.get("tags", ()))
    candidate_payload["triggers"] = tuple(candidate_payload.get("triggers", ()))
    candidate = MemoryCandidate(**candidate_payload)
    result = route_candidates([candidate], store, queue, auto_write_confidence=0.85)
    if result["auto_approved"] == 1:
        return {"status": "auto_approved"}
    if result["queued"] == 1:
        return {"status": "queued"}
    return {"status": "discarded"}
