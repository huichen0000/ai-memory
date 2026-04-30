from __future__ import annotations

from pathlib import Path

from ai_memory.adapters.generic_transcript import GenericTranscriptAdapter


class CodexCliAdapter(GenericTranscriptAdapter):
    name = "codex-cli"

    def __init__(self, home: Path | None = None):
        self.home = home or Path.home()

    def discover(self) -> list[Path]:
        sessions = self.home / ".codex" / "sessions"
        if not sessions.exists():
            return []
        return sorted(path for path in sessions.rglob("*") if path.is_file())
