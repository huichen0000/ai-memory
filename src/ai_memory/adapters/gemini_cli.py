from __future__ import annotations

from pathlib import Path

from ai_memory.adapters.generic_transcript import GenericTranscriptAdapter
from ai_memory.privacy.sensitive_paths import is_sensitive_path


class GeminiCliAdapter(GenericTranscriptAdapter):
    name = "gemini-cli"

    def __init__(self, home: Path | None = None):
        self.home = home or Path.home()

    def discover(self) -> list[Path]:
        root = self.home / ".gemini"
        if not root.exists():
            return []
        allowed_suffixes = {".md", ".json", ".jsonl", ".txt"}
        return sorted(path for path in root.rglob("*") if _is_discoverable(path, root, allowed_suffixes))


def _is_discoverable(path: Path, root: Path, allowed_suffixes: set[str]) -> bool:
    if path.is_symlink():
        return False
    try:
        resolved_path = path.resolve(strict=True)
    except OSError:
        return False
    return (
        path.is_file()
        and path.suffix.lower() in allowed_suffixes
        and not any(part.startswith(".") for part in path.relative_to(root).parts)
        and not is_sensitive_path(path)
        and not is_sensitive_path(resolved_path)
    )
