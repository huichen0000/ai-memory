from __future__ import annotations

import hashlib
from pathlib import Path

from ai_memory.core.models import NormalizedMessage, NormalizedTranscript
from ai_memory.privacy.redactor import redact_secrets


class GenericTranscriptAdapter:
    name = "generic"

    def discover(self) -> list[Path]:
        return []

    def normalize(self, source: Path) -> NormalizedTranscript:
        text = redact_secrets(source.read_text(encoding="utf-8"))
        messages = []
        for line in text.splitlines():
            if line.startswith("User:"):
                messages.append(NormalizedMessage(role="user", content=line.removeprefix("User:").strip()))
            elif line.startswith("Assistant:"):
                messages.append(NormalizedMessage(role="assistant", content=line.removeprefix("Assistant:").strip()))
        if not messages:
            messages.append(NormalizedMessage(role="transcript", content=text))
        session_id = "sess_" + hashlib.sha1(str(source.resolve()).encode("utf-8")).hexdigest()[:16]
        return NormalizedTranscript(
            session_id=session_id,
            client=self.name,
            source_path=str(source),
            messages=tuple(messages),
        )
