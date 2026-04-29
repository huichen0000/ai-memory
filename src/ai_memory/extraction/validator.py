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
    if redact_secrets(candidate.content) != candidate.content:
        raise ValueError("candidate content contains sensitive material")
