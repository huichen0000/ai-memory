from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

BUILT_IN_CLIENTS = ("claude-code", "codex-cli", "gemini-cli")
TRANSCRIPT_SUFFIXES = {".md", ".txt", ".json", ".jsonl"}


@dataclass(frozen=True)
class HistorySource:
    client: str
    path: Path


@dataclass(frozen=True)
class HistoryInitOptions:
    clients: tuple[str, ...]
    include_generic: tuple[Path, ...]
    review_only: bool = True
    auto_write_low_risk: bool = False
    limit: int | None = None
    dry_run: bool = False

    def __post_init__(self) -> None:
        if self.review_only and self.auto_write_low_risk:
            raise ValueError("--review-only and --auto-write-low-risk are mutually exclusive")
        if self.limit is not None and self.limit < 1:
            raise ValueError("--limit must be greater than zero")


@dataclass(frozen=True)
class HistoryInitSummary:
    clients_scanned: int = 0
    sources_found: int = 0
    sources_processed: int = 0
    transcripts_archived: int = 0
    transcripts_skipped: int = 0
    extraction_skipped: int = 0
    candidates_extracted: int = 0
    review_queued: int = 0
    auto_written: int = 0
    discarded: int = 0
    errors: tuple[str, ...] = ()


def parse_clients(value: str) -> tuple[str, ...]:
    raw_clients = tuple(part.strip() for part in value.split(",") if part.strip())
    clients = BUILT_IN_CLIENTS if raw_clients == ("all",) else raw_clients
    unsupported = [client for client in clients if client not in BUILT_IN_CLIENTS]
    if unsupported:
        raise ValueError(f"Unsupported history client: {unsupported[0]}")
    return clients


def collect_generic_sources(paths: tuple[Path, ...]) -> list[HistorySource]:
    sources: list[HistorySource] = []
    for path in paths:
        if path.is_file() and _is_transcript_like(path):
            sources.append(HistorySource(client="generic", path=path))
        elif path.is_dir():
            for candidate in sorted(path.rglob("*")):
                if candidate.is_file() and _is_transcript_like(candidate) and not _has_hidden_part(candidate.relative_to(path)):
                    sources.append(HistorySource(client="generic", path=candidate))
    return sources


def _is_transcript_like(path: Path) -> bool:
    return not path.name.startswith(".") and path.suffix.lower() in TRANSCRIPT_SUFFIXES


def _has_hidden_part(path: Path) -> bool:
    return any(part.startswith(".") for part in path.parts)
