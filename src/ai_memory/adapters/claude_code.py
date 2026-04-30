from __future__ import annotations

import json
from pathlib import Path

from ai_memory.adapters.generic_transcript import GenericTranscriptAdapter
from ai_memory.core.models import NormalizedMessage, NormalizedTranscript


class ClaudeCodeAdapter(GenericTranscriptAdapter):
    name = "claude-code"

    def __init__(self, home: Path | None = None):
        self.home = home or Path.home()

    def discover(self) -> list[Path]:
        projects = self.home / ".claude" / "projects"
        if not projects.exists():
            return []
        return sorted(projects.rglob("*.jsonl"))

    def normalize(self, source: Path) -> NormalizedTranscript:
        messages: list[NormalizedMessage] = []
        for line in source.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            role = data.get("type", data.get("role", "event"))
            content = data.get("message", data.get("content", ""))
            if isinstance(content, dict):
                content = json.dumps(content, ensure_ascii=False)
            messages.append(NormalizedMessage(role=str(role), content=str(content)))
        return NormalizedTranscript(
            session_id=f"sess_{source.stem}",
            client=self.name,
            source_path=str(source),
            messages=tuple(messages),
        )
