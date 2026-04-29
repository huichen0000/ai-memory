from __future__ import annotations

from ai_memory.core.models import MemoryCandidate
from ai_memory.core.policy import route_candidate
from ai_memory.extraction.validator import validate_candidate
from ai_memory.review.queue import ReviewQueue
from ai_memory.store.sqlite import SQLiteMemoryStore


def route_candidates(
    candidates: list[MemoryCandidate],
    store: SQLiteMemoryStore,
    queue: ReviewQueue,
    auto_write_confidence: float,
) -> dict[str, int]:
    counts = {"auto_approved": 0, "queued": 0, "discarded": 0}
    for candidate in candidates:
        try:
            validate_candidate(candidate)
        except ValueError:
            counts["discarded"] += 1
            continue
        decision = route_candidate(candidate, auto_write_confidence)
        if decision.action == "auto_write":
            store.create_memory(candidate, status="auto_approved", change_reason=decision.reason)
            counts["auto_approved"] += 1
        elif decision.action == "review":
            queue.enqueue(candidate, decision.reason)
            counts["queued"] += 1
        else:
            counts["discarded"] += 1
    return counts
