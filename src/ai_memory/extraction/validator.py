from __future__ import annotations

from ai_memory.core.models import MemoryCandidate
from ai_memory.core.uri import validate_memory_uri
from ai_memory.privacy.redactor import redact_secrets


def validate_candidate(candidate: MemoryCandidate) -> None:
    validate_memory_uri(candidate.uri)
    if not candidate.content.strip():
        raise ValueError("candidate content is required")
    if not candidate.evidence.strip():
        raise ValueError("candidate evidence is required")
    if not 0 <= candidate.confidence <= 1:
        raise ValueError("candidate confidence must be between 0 and 1")
    _reject_sensitive_text("content", candidate.content)
    _reject_sensitive_text("summary", candidate.summary)
    _reject_sensitive_text("evidence", candidate.evidence)
    for tag in candidate.tags:
        _reject_sensitive_text("tags", tag)
    for trigger in candidate.triggers:
        _reject_sensitive_text("triggers", trigger)


def _reject_sensitive_text(field: str, value: str) -> None:
    if redact_secrets(value) != value:
        raise ValueError(f"candidate {field} contains sensitive material")
