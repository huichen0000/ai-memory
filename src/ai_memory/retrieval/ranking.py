from __future__ import annotations

from ai_memory.core.models import MemoryRecord


STATUS_WEIGHT = {"approved": 50, "auto_approved": 30}
SCOPE_WEIGHT = {"branch": 100, "path": 80, "project": 70, "tool": 40, "global": 35, "org": 35, "system": 25}


def rank_records(records: list[MemoryRecord]) -> list[MemoryRecord]:
    return sorted(
        records,
        key=lambda record: (
            STATUS_WEIGHT.get(record.status, 0) + SCOPE_WEIGHT.get(record.scope, 0) + int(record.confidence * 10),
            record.updated_at,
        ),
        reverse=True,
    )
