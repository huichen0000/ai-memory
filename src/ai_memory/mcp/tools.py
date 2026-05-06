from __future__ import annotations

import fnmatch
import re
import sqlite3
from collections.abc import Mapping
from dataclasses import asdict
from typing import Any

from ai_memory.core.models import MemoryCandidate
from ai_memory.core.uri import parse_memory_uri
from ai_memory.extraction.router import route_candidates
from ai_memory.retrieval.assembler import assemble_context
from ai_memory.retrieval.ranking import rank_records_for_context
from ai_memory.review.queue import ReviewQueue
from ai_memory.store.sqlite import SQLiteMemoryStore

MAX_LIMIT = 50


def _tokenize(value: str) -> tuple[str, ...]:
    seen: list[str] = []
    for token in re.findall(r"[a-z0-9_-]+", value.lower()):
        if token not in seen:
            seen.append(token)
    return tuple(seen)


def _clamp_limit(value: int) -> int:
    return max(1, min(int(value), MAX_LIMIT))


def _safe_search(store: SQLiteMemoryStore, query: str, limit: int) -> list[Any]:
    sanitized_limit = _clamp_limit(limit)
    if not query.strip():
        return []
    tokens = _tokenize(query)
    if not tokens:
        return []
    seen: set[str] = set()
    records = []
    candidate_limit = max(sanitized_limit * 5, MAX_LIMIT)
    for token in tokens:
        try:
            matches = store.search(token, candidate_limit)
        except sqlite3.OperationalError:
            continue
        for record in matches:
            if record.id not in seen:
                seen.add(record.id)
                records.append(record)
    return records


def memory_search(
    store: SQLiteMemoryStore,
    query: str,
    limit: int = 10,
    environment: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    if environment is None:
        return {"items": [], "error": "environment is required for scoped retrieval"}
    sanitized_limit = _clamp_limit(limit)
    search_records = _safe_search(store, query, sanitized_limit)
    contextual_records = store.list_contextual(environment, sanitized_limit)
    records_by_id = {record.id: record for record in [*contextual_records, *search_records]}
    records = _filter_records_for_environment(list(records_by_id.values()), environment)
    records = rank_records_for_context(records, query, environment)[:sanitized_limit]
    return {"items": [asdict(record) for record in records]}


def memory_context(
    store: SQLiteMemoryStore,
    prompt: str,
    max_items: int = 12,
    environment: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    sanitized_limit = _clamp_limit(max_items)
    if environment is None:
        return {
            "context": assemble_context([]),
            "items": [],
            "error": "environment is required for scoped retrieval",
        }
    search_records = _safe_search(store, prompt, sanitized_limit)
    contextual_records = store.list_contextual(environment, sanitized_limit)
    records_by_id = {record.id: record for record in [*contextual_records, *search_records]}
    records = _filter_records_for_environment(list(records_by_id.values()), environment)
    records = rank_records_for_context(records, prompt, environment)[:sanitized_limit]
    return {"context": assemble_context(records), "items": [asdict(record) for record in records]}


def memory_read(
    store: SQLiteMemoryStore,
    memory_id: str,
    environment: dict[str, str | None] | None = None,
    trusted_environment: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    effective_environment = trusted_environment or environment
    if effective_environment is None:
        return {"item": None, "error": "environment is required for scoped retrieval"}
    record = store.get_memory(memory_id)
    if record is None or record.status not in {"approved", "auto_approved"}:
        return {"item": None}
    if not _record_matches_environment(record, effective_environment):
        return {"item": None}
    return {"item": asdict(record)}


def memory_write(
    store: SQLiteMemoryStore,
    queue: ReviewQueue,
    payload: dict[str, Any],
    trusted_environment: dict[str, str | None] | None = None,
    review_only: bool = False,
) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {"status": "discarded", "error": "payload must be an object"}
    try:
        candidate_payload = dict(payload)
        trusted_write = trusted_environment is not None
        if trusted_write:
            candidate_payload = _bind_payload_to_environment(candidate_payload, trusted_environment)
        candidate_payload["tags"] = _normalize_text_items(candidate_payload.get("tags", ()), "tags")
        candidate_payload["triggers"] = _normalize_text_items(candidate_payload.get("triggers", ()), "triggers")
        candidate = MemoryCandidate(**candidate_payload)
        force_review = review_only or not trusted_write
        auto_write_confidence = 1.01 if force_review else 0.85
        result = route_candidates([candidate], store, queue, auto_write_confidence=auto_write_confidence)
    except (TypeError, ValueError) as exc:
        return {"status": "discarded", "error": _safe_error(exc)}
    if result["auto_approved"] == 1:
        return {"status": "auto_approved"}
    if result["queued"] == 1:
        return {"status": "queued"}
    return {"status": "discarded"}


def _bind_payload_to_environment(
    payload: dict[str, Any],
    environment: dict[str, str | None],
) -> dict[str, Any]:
    repo_id = environment.get("repo_id")
    branch = environment.get("branch")
    parsed = parse_memory_uri(str(payload.get("uri", "")))
    if payload.get("scope") != parsed.namespace:
        raise ValueError("memory write scope does not match URI namespace")
    if parsed.namespace in {"project", "branch", "path"}:
        uri_repo_id = _repo_id_from_parsed_uri(parsed.namespace, parsed.authority, parsed.parts)
        if repo_id is None or uri_repo_id != repo_id:
            raise ValueError("memory write URI does not match trusted environment")
        payload["repo_id"] = repo_id
    if parsed.namespace == "branch":
        branch_index = _branch_index(parsed.authority)
        if branch is None or len(parsed.parts) <= branch_index or parsed.parts[branch_index] != branch:
            raise ValueError("memory write branch does not match trusted environment")
        payload["branch"] = branch
    elif parsed.namespace in {"project", "path"}:
        payload["branch"] = None
    return payload


def _repo_id_from_parsed_uri(namespace: str, authority: str, parts: tuple[str, ...]) -> str:
    repo_part_count = 2 if "." in authority else 1
    if namespace == "branch":
        return "/".join((authority, *parts[:repo_part_count]))
    return "/".join((authority, *parts[:repo_part_count]))


def _branch_index(authority: str) -> int:
    return 2 if "." in authority else 1


def _normalize_text_items(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field} must be a list or tuple of strings")
    if not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field} must contain only strings")
    return tuple(value)


def _filter_records_for_environment(
    records: list[Any],
    environment: dict[str, str | None],
) -> list[Any]:
    return [record for record in records if _record_matches_environment(record, environment)]


def _record_matches_environment(record: Any, environment: dict[str, str | None]) -> bool:
    repo_id = environment.get("repo_id")
    branch = environment.get("branch")
    relative_path = environment.get("relative_path")
    if not _is_context_path_match(record.scope, record.path_glob, relative_path):
        return False
    if record.scope in {"global", "system"}:
        return True
    if record.scope == "branch":
        return repo_id is not None and branch is not None and record.repo_id == repo_id and record.branch == branch
    return repo_id is not None and record.repo_id == repo_id


def _is_context_path_match(scope: str, path_glob: str | None, relative_path: str | None) -> bool:
    if scope != "path":
        return True
    if relative_path is None:
        return False
    return _path_matches(path_glob, relative_path)


def _path_matches(path_glob: str | None, relative_path: str) -> bool:
    if path_glob is None:
        return False
    if fnmatch.fnmatch(relative_path, path_glob):
        return True
    if "/**/" in path_glob:
        return fnmatch.fnmatch(relative_path, path_glob.replace("/**/", "/"))
    return False


def _safe_error(exc: Exception) -> str:
    message = str(exc)
    if "contains sensitive material" in message:
        return message
    if isinstance(exc, TypeError):
        return "payload is malformed"
    return message
