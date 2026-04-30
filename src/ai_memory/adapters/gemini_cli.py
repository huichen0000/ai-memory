from __future__ import annotations

from pathlib import Path

from ai_memory.adapters.generic_transcript import GenericTranscriptAdapter


class GeminiCliAdapter(GenericTranscriptAdapter):
    name = "gemini-cli"

    def __init__(self, home: Path | None = None):
        self.home = home or Path.home()

    def discover(self) -> list[Path]:
        root = self.home / ".gemini"
        if not root.exists():
            return []
        allowed_suffixes = {".md", ".json", ".jsonl", ".txt"}
        return sorted(
            path
            for path in root.rglob("*")
            if path.is_file()
            and path.suffix in allowed_suffixes
            and not any(part.startswith(".") for part in path.relative_to(root).parts)
            and "code_tracker" not in path.relative_to(root).parts
        )
