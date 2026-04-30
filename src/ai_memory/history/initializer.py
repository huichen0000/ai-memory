from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ai_memory.adapters.claude_code import ClaudeCodeAdapter
from ai_memory.adapters.codex_cli import CodexCliAdapter
from ai_memory.adapters.gemini_cli import GeminiCliAdapter
from ai_memory.adapters.generic_transcript import GenericTranscriptAdapter
from ai_memory.core.config import AppConfig
from ai_memory.core.models import MemoryCandidate, NormalizedTranscript
from ai_memory.core.policy import route_candidate
from ai_memory.extraction.validator import validate_candidate
from ai_memory.review.queue import ReviewQueue
from ai_memory.store.sqlite import SQLiteMemoryStore

BUILT_IN_CLIENTS = ("claude-code", "codex-cli", "gemini-cli")
TRANSCRIPT_SUFFIXES = {".md", ".txt", ".json", ".jsonl"}


class ExtractorProvider(Protocol):
    def extract(self, transcript: NormalizedTranscript) -> list[MemoryCandidate]:
        ...


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
        if not self.review_only and not self.auto_write_low_risk:
            raise ValueError("either --review-only or --auto-write-low-risk is required")
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


def archive_target_for(raw_dir: Path, source: HistorySource) -> Path:
    client_dir = raw_dir / source.client
    first_target = client_dir / source.path.name
    if not first_target.exists():
        return first_target
    digest = hashlib.sha1(str(source.path.resolve()).encode("utf-8")).hexdigest()[:8]
    return client_dir / f"{source.path.stem}-{digest}{source.path.suffix}"


def run_history_init(
    *,
    options: HistoryInitOptions,
    config: AppConfig,
    source_home: Path,
    store: SQLiteMemoryStore,
    queue: ReviewQueue,
    extractor: ExtractorProvider | None,
) -> HistoryInitSummary:
    errors: list[str] = []
    sources = _discover_sources(options, source_home, errors)
    if options.limit is not None:
        sources = sources[: options.limit]
    if options.dry_run:
        return HistoryInitSummary(
            clients_scanned=len(options.clients),
            sources_found=len(sources),
            errors=tuple(errors),
        )

    processed = 0
    archived = 0
    skipped = 0
    extraction_skipped = 0
    candidates_extracted = 0
    queued = 0
    auto_written = 0
    discarded = 0
    for source in sources:
        try:
            _archive_source(config.raw_dir, source)
            archived += 1
            processed += 1
            if extractor is None:
                extraction_skipped += 1
                continue
            transcript = _normalize_source(source)
            candidates = extractor.extract(transcript)
            candidates_extracted += len(candidates)
            for candidate in candidates:
                try:
                    validate_candidate(candidate)
                except ValueError as exc:
                    discarded += 1
                    errors.append(str(exc))
                    continue
                if options.review_only:
                    queue.enqueue(candidate, f"historical import from {source.client} requires review")
                    queued += 1
                else:
                    decision = route_candidate(candidate, config.auto_write_confidence)
                    if decision.action == "auto_write":
                        store.create_memory(
                            candidate,
                            status="auto_approved",
                            change_reason=f"historical import auto-write from {source.client}",
                        )
                        auto_written += 1
                    elif decision.action == "review":
                        queue.enqueue(candidate, f"historical import from {source.client} requires review")
                        queued += 1
                    else:
                        discarded += 1
        except (OSError, UnicodeDecodeError) as exc:
            skipped += 1
            errors.append(f"{source.client}: {source.path}: {exc}")
        except Exception as exc:
            errors.append(f"{source.client}: {source.path}: {exc}")

    return HistoryInitSummary(
        clients_scanned=len(options.clients),
        sources_found=len(sources),
        sources_processed=processed,
        transcripts_archived=archived,
        transcripts_skipped=skipped,
        extraction_skipped=extraction_skipped,
        candidates_extracted=candidates_extracted,
        review_queued=queued,
        auto_written=auto_written,
        discarded=discarded,
        errors=tuple(errors),
    )


def _discover_sources(options: HistoryInitOptions, source_home: Path, errors: list[str]) -> list[HistorySource]:
    sources: list[HistorySource] = []
    for client in options.clients:
        try:
            adapter = _adapter_for(client, source_home)
            sources.extend(HistorySource(client=client, path=path) for path in adapter.discover())
        except Exception as exc:
            errors.append(f"{client}: discovery failed: {exc}")
    sources.extend(collect_generic_sources(options.include_generic))
    return sorted(sources, key=lambda source: (source.client, str(source.path)))


def _adapter_for(client: str, home: Path):
    if client == "claude-code":
        return ClaudeCodeAdapter(home=home)
    if client == "codex-cli":
        return CodexCliAdapter(home=home)
    if client == "gemini-cli":
        return GeminiCliAdapter(home=home)
    raise ValueError(f"Unsupported history client: {client}")


def _normalize_source(source: HistorySource) -> NormalizedTranscript:
    if source.client == "generic":
        return GenericTranscriptAdapter().normalize(source.path)
    return _adapter_for(source.client, source.path.parent).normalize(source.path)


def _archive_source(raw_dir: Path, source: HistorySource) -> Path:
    source.path.read_text(encoding="utf-8")
    target = archive_target_for(raw_dir, source)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source.path, target)
    return target


def _is_transcript_like(path: Path) -> bool:
    return not path.name.startswith(".") and path.suffix.lower() in TRANSCRIPT_SUFFIXES


def _has_hidden_part(path: Path) -> bool:
    return any(part.startswith(".") for part in path.parts)
