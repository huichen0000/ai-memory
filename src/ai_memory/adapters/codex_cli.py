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
        allowed_suffixes = {".md", ".json", ".jsonl", ".txt"}
        return sorted(
            path
            for path in sessions.rglob("*")
            if path.is_file()
            and not path.is_symlink()
            and path.suffix.lower() in allowed_suffixes
            and not any(part.startswith(".") for part in path.relative_to(sessions).parts)
        )
