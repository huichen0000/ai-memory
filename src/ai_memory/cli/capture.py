from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_memory.adapters.claude_code import ClaudeCodeAdapter
from ai_memory.adapters.codex_cli import CodexCliAdapter
from ai_memory.adapters.gemini_cli import GeminiCliAdapter
from ai_memory.adapters.generic_transcript import GenericTranscriptAdapter
from ai_memory.core.config import load_config
from ai_memory.extraction.providers.command import CommandExtractorProvider
from ai_memory.extraction.router import route_candidates
from ai_memory.extraction.validator import validate_candidate
from ai_memory.history.initializer import HistorySource, archive_target_for
from ai_memory.privacy.redactor import redact_secrets
from ai_memory.review.queue import ReviewQueue
from ai_memory.store.sqlite import SQLiteMemoryStore


BUILT_IN_CLIENTS = {"claude-code": ClaudeCodeAdapter, "codex-cli": CodexCliAdapter, "gemini-cli": GeminiCliAdapter}


@dataclass(frozen=True)
class CaptureSummary:
    archived: bool = False
    skipped_archive: bool = False
    extraction_skipped: bool = False
    candidates_extracted: int = 0
    review_queued: int = 0
    auto_written: int = 0
    discarded: int = 0
    error: str | None = None


def _adapter_for(client: str, home: Path):
    cls = BUILT_IN_CLIENTS.get(client, GenericTranscriptAdapter)
    return cls(home=home)


def _latest_transcript(home: Path, client: str) -> Path | None:
    adapter = _adapter_for(client, home)
    sources = adapter.discover()
    if not sources:
        return None
    return sorted(sources, key=lambda p: p.stat().st_mtime, reverse=True)[0]


def run_capture(
    *,
    client: str,
    home: Path,
    source_home: Path,
    session_path: str | None,
    no_archive: bool,
    no_extract: bool,
    review_only: bool,
    auto_write_low_risk: bool,
    redact_archive: bool = False,
) -> int:
    config = load_config(home)
    store = SQLiteMemoryStore(config.store_path)
    store.initialize()
    queue = ReviewQueue(config.review_queue_path)

    if session_path:
        transcript_path = Path(session_path)
    else:
        transcript_path = _latest_transcript(source_home, client)
        if transcript_path is None:
            print(f"No transcript found for client: {client}")
            return 2

    source = HistorySource(client=client, path=transcript_path)
    summary = _capture_single(
        source=source,
        config=config,
        store=store,
        queue=queue,
        no_archive=no_archive,
        no_extract=no_extract,
        review_only=review_only,
        auto_write_low_risk=auto_write_low_risk,
        redact_archive=redact_archive,
    )
    _print_capture_summary(summary, config.raw_dir, client)
    return 0 if summary.error is None else 2


def _capture_single(
    *,
    source: HistorySource,
    config: Any,
    store: SQLiteMemoryStore,
    queue: ReviewQueue,
    no_archive: bool,
    no_extract: bool,
    review_only: bool,
    auto_write_low_risk: bool,
    redact_archive: bool = False,
) -> CaptureSummary:
    try:
        resolved = source.path.resolve(strict=True)
    except OSError as exc:
        return CaptureSummary(error=f"Unable to resolve transcript path: {source.path}: {exc}")

    if not no_archive:
        try:
            target = archive_target_for(config.raw_dir, source)
            target.parent.mkdir(parents=True, exist_ok=True)
            if redact_archive:
                content = resolved.read_text(encoding="utf-8")
                target.write_text(redact_secrets(content), encoding="utf-8")
            else:
                import shutil
                shutil.copyfile(resolved, target)
            archived = True
        except Exception as exc:
            return CaptureSummary(error=f"Archive failed: {exc}")
    else:
        archived = False

    if no_extract:
        return CaptureSummary(archived=archived, skipped_archive=not archived)

    extractor = None
    if config.extractor_provider == "command" and config.extractor_command:
        extractor = CommandExtractorProvider(config.extractor_command)

    if extractor is None:
        return CaptureSummary(archived=archived, skipped_archive=not archived, extraction_skipped=True)

    try:
        adapter = _adapter_for(source.client, source.path.parent)
        transcript = adapter.normalize(source.path)
    except Exception as exc:
        return CaptureSummary(archived=archived, skipped_archive=not archived, error=f"Normalize failed: {exc}")

    try:
        candidates = extractor.extract(transcript)
    except Exception as exc:
        return CaptureSummary(archived=archived, skipped_archive=not archived, error=f"Extract failed: {exc}")

    candidates_extracted = len(candidates)
    routed = route_candidates(
        candidates,
        store,
        queue,
        auto_write_confidence=1.01 if review_only or not auto_write_low_risk else config.auto_write_confidence,
    )

    for candidate in candidates:
        try:
            validate_candidate(candidate)
        except ValueError:
            routed["discarded"] += 1

    return CaptureSummary(
        archived=archived,
        skipped_archive=not archived,
        extraction_skipped=False,
        candidates_extracted=candidates_extracted,
        review_queued=routed.get("queued", 0),
        auto_written=routed.get("auto_approved", 0),
        discarded=routed.get("discarded", 0),
    )


def _print_capture_summary(summary: CaptureSummary, raw_dir: Path, client: str) -> None:
    print(f"Capture complete for {client}.")
    if summary.error:
        print(f"Error: {summary.error}")
        return
    if summary.archived:
        print(f"Archived to: {raw_dir}")
    elif summary.skipped_archive:
        print("Archive skipped (--no-archive).")
    if summary.extraction_skipped:
        print("Extraction skipped (no extractor configured or --no-extract).")
    else:
        print(f"Candidates extracted: {summary.candidates_extracted}")
        print(f"Review queued: {summary.review_queued}")
        print(f"Auto-written: {summary.auto_written}")
        print(f"Discarded: {summary.discarded}")