from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

MemoryStatus = Literal["proposed", "approved", "auto_approved", "rejected", "archived", "expired", "conflicted"]
RiskLevel = Literal["low", "medium", "high"]
RouteAction = Literal["auto_write", "review", "discard"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


@dataclass(frozen=True)
class MemoryCandidate:
    uri: str
    type: str
    scope: str
    content: str
    summary: str
    confidence: float
    risk: RiskLevel
    evidence: str
    tags: tuple[str, ...] = field(default_factory=tuple)
    triggers: tuple[str, ...] = field(default_factory=tuple)
    repo_id: str | None = None
    branch: str | None = None
    path_glob: str | None = None
    expires_at: str | None = None
    source_client: str | None = None
    session_id: str | None = None
    transcript_ref: str | None = None


@dataclass(frozen=True)
class MemoryRecord:
    id: str
    uri: str
    type: str
    scope: str
    content: str
    summary: str
    status: MemoryStatus
    confidence: float
    risk: RiskLevel
    repo_id: str | None
    branch: str | None
    path_glob: str | None
    expires_at: str | None
    created_at: str
    updated_at: str
    triggers: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RouteDecision:
    action: RouteAction
    reason: str


@dataclass(frozen=True)
class NormalizedMessage:
    role: str
    content: str
    timestamp: str | None = None
    name: str | None = None


@dataclass(frozen=True)
class NormalizedTranscript:
    session_id: str
    client: str
    source_path: str
    messages: tuple[NormalizedMessage, ...]
    cwd: str | None = None
    repo_id: str | None = None
    branch: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
