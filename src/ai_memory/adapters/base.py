from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ai_memory.core.models import NormalizedTranscript


class ClientAdapter(Protocol):
    name: str

    def discover(self) -> list[Path]:
        raise NotImplementedError

    def normalize(self, source: Path) -> NormalizedTranscript:
        raise NotImplementedError
