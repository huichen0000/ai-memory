from __future__ import annotations

import re

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


def rank_records_for_context(
    records: list[MemoryRecord],
    prompt: str,
    environment: dict[str, str | None],
) -> list[MemoryRecord]:
    prompt_tokens = set(re.findall(r"[a-z0-9_-]+", prompt.lower()))
    repo_id = environment.get("repo_id")
    branch = environment.get("branch")
    return sorted(
        records,
        key=lambda record: (
            _scope_score(record, repo_id, branch)
            + _trigger_score(record, prompt_tokens)
            + STATUS_WEIGHT.get(record.status, 0)
            + int(record.confidence * 10),
            record.updated_at,
        ),
        reverse=True,
    )


def _scope_score(record: MemoryRecord, repo_id: str | None, branch: str | None) -> int:
    if repo_id and branch and record.repo_id == repo_id and record.branch == branch:
        return 160
    if repo_id and record.repo_id == repo_id:
        return 140
    return SCOPE_WEIGHT.get(record.scope, 0)


def _trigger_score(record: MemoryRecord, prompt_tokens: set[str]) -> int:
    trigger_tokens = {token for trigger in record.triggers for token in re.findall(r"[a-z0-9_-]+", trigger.lower())}
    if prompt_tokens & trigger_tokens:
        return 60
    haystack = f"{record.uri} {record.summary} {record.content}".lower()
    return 30 if any(token in haystack for token in prompt_tokens) else 0
