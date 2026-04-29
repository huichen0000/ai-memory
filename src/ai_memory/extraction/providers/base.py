from __future__ import annotations

from typing import Protocol

from ai_memory.core.models import MemoryCandidate, NormalizedTranscript


class ExtractorProvider(Protocol):
    def extract(self, transcript: NormalizedTranscript) -> list[MemoryCandidate]:
        raise NotImplementedError
