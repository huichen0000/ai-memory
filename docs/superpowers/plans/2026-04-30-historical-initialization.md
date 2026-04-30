# Historical Initialization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `ai-memory history init` so users can automatically discover historical AI-tool transcripts, archive them, extract candidate memories, and route them safely through review or low-risk auto-write.

**Architecture:** Add a focused `ai_memory.history.initializer` orchestration module and keep `cli/main.py` thin. Reuse existing adapters, redaction, extractor provider, candidate validation, policy routing, review queue, and SQLite store instead of duplicating those responsibilities.

**Tech Stack:** Python 3.11+, argparse CLI, pathlib, dataclasses, SQLite store, JSONL review queue, pytest.

---

## File Structure

- Create `src/ai_memory/history/__init__.py`
  - Package marker for the new history feature.

- Create `src/ai_memory/history/initializer.py`
  - Owns dataclasses, client parsing, source discovery, archive naming, transcript normalization, extraction, routing, and summary construction.
  - Public API expected by CLI:
    - `BUILT_IN_CLIENTS`
    - `HistorySource`
    - `HistoryInitOptions`
    - `HistoryInitSummary`
    - `parse_clients()`
    - `run_history_init()`

- Modify `src/ai_memory/cli/main.py`
  - Add `history init` subcommand and arguments.
  - Convert CLI args into `HistoryInitOptions`.
  - Initialize config/store/queue and call `run_history_init()`.
  - Print deterministic summary.

- Create `tests/unit/test_history_initializer.py`
  - Unit tests for parsing, dry-run behavior, archive naming, review-only routing, auto-write routing, generic include scanning, missing extractor behavior, and per-source resilience.

- Modify `tests/unit/test_adapters.py`
  - Add CLI tests for invalid history clients and invalid option combinations if those fit better at CLI level.

- Modify `README.md`
  - Add English usage docs and privacy warning for historical initialization.

- Modify `README_CN.md`
  - Add Chinese usage docs and privacy warning for historical initialization.

---

### Task 1: Add History Initializer Skeleton and Client Parsing

**Files:**
- Create: `src/ai_memory/history/__init__.py`
- Create: `src/ai_memory/history/initializer.py`
- Create: `tests/unit/test_history_initializer.py`

- [ ] **Step 1: Write failing tests for client parsing and generic discovery**

Create `tests/unit/test_history_initializer.py` with this initial content:

```python
from pathlib import Path

import pytest

from ai_memory.history.initializer import (
    BUILT_IN_CLIENTS,
    HistoryInitOptions,
    HistorySource,
    collect_generic_sources,
    parse_clients,
)


def test_parse_clients_all_resolves_built_ins():
    assert parse_clients("all") == BUILT_IN_CLIENTS


def test_parse_clients_accepts_comma_separated_subset():
    assert parse_clients("claude-code,gemini-cli") == ("claude-code", "gemini-cli")


def test_parse_clients_rejects_unknown_client():
    with pytest.raises(ValueError, match="Unsupported history client: unknown"):
        parse_clients("claude-code,unknown")


def test_history_options_reject_conflicting_routing_modes():
    with pytest.raises(ValueError, match="mutually exclusive"):
        HistoryInitOptions(
            clients=("claude-code",),
            include_generic=(),
            review_only=True,
            auto_write_low_risk=True,
            limit=None,
            dry_run=False,
        )


def test_collect_generic_sources_accepts_file_and_directory_and_skips_hidden(tmp_path: Path):
    direct = tmp_path / "chat.md"
    direct.write_text("User: remember pytest", encoding="utf-8")
    root = tmp_path / "logs"
    hidden_dir = root / ".hidden"
    hidden_dir.mkdir(parents=True)
    nested = root / "nested.jsonl"
    nested.write_text("{}\n", encoding="utf-8")
    ignored_suffix = root / "image.bin"
    ignored_suffix.write_bytes(b"\x00\x01")
    hidden_file = root / ".secret.md"
    hidden_file.write_text("hidden", encoding="utf-8")
    hidden_nested = hidden_dir / "chat.md"
    hidden_nested.write_text("hidden", encoding="utf-8")

    sources = collect_generic_sources((direct, root))

    assert sources == [HistorySource(client="generic", path=direct), HistorySource(client="generic", path=nested)]
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```bash
py -m pytest tests/unit/test_history_initializer.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'ai_memory.history'`.

- [ ] **Step 3: Add the history package marker**

Create `src/ai_memory/history/__init__.py`:

```python
"""Historical transcript initialization."""
```

- [ ] **Step 4: Implement dataclasses, client parsing, and generic source collection**

Create `src/ai_memory/history/initializer.py` with:

```python
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
```

- [ ] **Step 5: Run the focused tests and verify they pass**

Run:

```bash
py -m pytest tests/unit/test_history_initializer.py -v
```

Expected: PASS for all tests currently in `test_history_initializer.py`.

- [ ] **Step 6: Commit Task 1**

Run:

```bash
git add src/ai_memory/history/__init__.py src/ai_memory/history/initializer.py tests/unit/test_history_initializer.py
git commit -m "feat: add history initializer skeleton"
```

---

### Task 2: Add Discovery, Stable Archive Names, and Dry-Run Behavior

**Files:**
- Modify: `src/ai_memory/history/initializer.py`
- Modify: `tests/unit/test_history_initializer.py`

- [ ] **Step 1: Add failing tests for discovery, archive naming, and dry-run writes**

Append these tests to `tests/unit/test_history_initializer.py`:

```python
from ai_memory.core.config import init_home
from ai_memory.history.initializer import archive_target_for, run_history_init
from ai_memory.review.queue import ReviewQueue
from ai_memory.store.sqlite import SQLiteMemoryStore


def test_archive_target_for_uses_stable_suffix_for_duplicate_names(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    source_a = tmp_path / "a" / "session.jsonl"
    source_b = tmp_path / "b" / "session.jsonl"
    source_a.parent.mkdir()
    source_b.parent.mkdir()
    source_a.write_text("a", encoding="utf-8")
    source_b.write_text("b", encoding="utf-8")

    first = archive_target_for(raw_dir, HistorySource("claude-code", source_a))
    first.parent.mkdir(parents=True)
    first.write_text("archived", encoding="utf-8")
    second = archive_target_for(raw_dir, HistorySource("claude-code", source_b))

    assert first == raw_dir / "claude-code" / "session.jsonl"
    assert second.name.startswith("session-")
    assert second.suffix == ".jsonl"
    assert second != first


def test_history_init_dry_run_discovers_sources_without_writes(tmp_path: Path):
    home = tmp_path / ".ai-memory"
    config = init_home(home)
    projects = tmp_path / ".claude" / "projects" / "demo"
    projects.mkdir(parents=True)
    session = projects / "session.jsonl"
    session.write_text('{"type":"user","message":"Use pytest"}\n', encoding="utf-8")
    store = SQLiteMemoryStore(config.store_path)
    store.initialize()
    queue = ReviewQueue(config.review_queue_path)

    summary = run_history_init(
        options=HistoryInitOptions(
            clients=("claude-code",),
            include_generic=(),
            review_only=True,
            auto_write_low_risk=False,
            limit=None,
            dry_run=True,
        ),
        config=config,
        source_home=tmp_path,
        store=store,
        queue=queue,
        extractor=None,
    )

    assert summary.clients_scanned == 1
    assert summary.sources_found == 1
    assert summary.sources_processed == 0
    assert summary.transcripts_archived == 0
    assert summary.extraction_skipped == 0
    assert not any((home / "raw").rglob("*.jsonl"))
    assert queue.list_pending() == []
    assert store.search("pytest", limit=10) == []


def test_history_init_archives_and_reports_missing_extractor(tmp_path: Path):
    home = tmp_path / ".ai-memory"
    config = init_home(home)
    transcript = tmp_path / "chat.md"
    transcript.write_text("User: Use pytest for tests", encoding="utf-8")
    store = SQLiteMemoryStore(config.store_path)
    store.initialize()
    queue = ReviewQueue(config.review_queue_path)

    summary = run_history_init(
        options=HistoryInitOptions(
            clients=(),
            include_generic=(transcript,),
            review_only=True,
            auto_write_low_risk=False,
            limit=None,
            dry_run=False,
        ),
        config=config,
        source_home=tmp_path,
        store=store,
        queue=queue,
        extractor=None,
    )

    assert summary.clients_scanned == 0
    assert summary.sources_found == 1
    assert summary.sources_processed == 1
    assert summary.transcripts_archived == 1
    assert summary.extraction_skipped == 1
    assert (home / "raw" / "generic" / "chat.md").read_text(encoding="utf-8") == "User: Use pytest for tests"
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```bash
py -m pytest tests/unit/test_history_initializer.py -v
```

Expected: FAIL because `archive_target_for` and `run_history_init` are not implemented.

- [ ] **Step 3: Implement discovery, archive naming, dry-run, and missing-extractor path**

Replace `src/ai_memory/history/initializer.py` with this full version:

```python
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
    for source in sources:
        try:
            _archive_source(config.raw_dir, source)
            archived += 1
            processed += 1
            if extractor is None:
                extraction_skipped += 1
                continue
        except (OSError, UnicodeDecodeError) as exc:
            skipped += 1
            errors.append(f"{source.client}: {source.path}: {exc}")

    return HistoryInitSummary(
        clients_scanned=len(options.clients),
        sources_found=len(sources),
        sources_processed=processed,
        transcripts_archived=archived,
        transcripts_skipped=skipped,
        extraction_skipped=extraction_skipped,
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
```

- [ ] **Step 4: Run the focused tests and verify they pass**

Run:

```bash
py -m pytest tests/unit/test_history_initializer.py -v
```

Expected: PASS for all tests in `test_history_initializer.py`.

- [ ] **Step 5: Commit Task 2**

Run:

```bash
git add src/ai_memory/history/initializer.py tests/unit/test_history_initializer.py
git commit -m "feat: discover and archive historical transcripts"
```

---

### Task 3: Add Extraction and Review-Only Routing

**Files:**
- Modify: `src/ai_memory/history/initializer.py`
- Modify: `tests/unit/test_history_initializer.py`

- [ ] **Step 1: Add failing tests for review-only extraction and per-source extractor failure resilience**

Append these tests to `tests/unit/test_history_initializer.py`:

```python
from ai_memory.core.models import MemoryCandidate


class StaticExtractor:
    def __init__(self, candidates: list[MemoryCandidate]):
        self.candidates = candidates

    def extract(self, transcript):
        return self.candidates


class FailingExtractor:
    def extract(self, transcript):
        raise ValueError("bad extractor output")


def low_risk_candidate() -> MemoryCandidate:
    return MemoryCandidate(
        uri="project://local/demo/commands",
        type="project_command",
        scope="project",
        content="Use pytest for tests.",
        summary="Use pytest.",
        confidence=0.9,
        risk="low",
        evidence="historical transcript stated test command",
    )


def test_history_init_review_only_queues_low_risk_candidate(tmp_path: Path):
    home = tmp_path / ".ai-memory"
    config = init_home(home)
    transcript = tmp_path / "chat.md"
    transcript.write_text("User: Use pytest for tests", encoding="utf-8")
    store = SQLiteMemoryStore(config.store_path)
    store.initialize()
    queue = ReviewQueue(config.review_queue_path)

    summary = run_history_init(
        options=HistoryInitOptions(
            clients=(),
            include_generic=(transcript,),
            review_only=True,
            auto_write_low_risk=False,
            limit=None,
            dry_run=False,
        ),
        config=config,
        source_home=tmp_path,
        store=store,
        queue=queue,
        extractor=StaticExtractor([low_risk_candidate()]),
    )

    assert summary.candidates_extracted == 1
    assert summary.review_queued == 1
    assert summary.auto_written == 0
    assert len(queue.list_pending()) == 1
    assert store.search("pytest", limit=10) == []
    assert "historical import from generic requires review" in queue.list_pending()[0].reason


def test_history_init_records_extractor_error_and_continues(tmp_path: Path):
    home = tmp_path / ".ai-memory"
    config = init_home(home)
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"
    first.write_text("User: one", encoding="utf-8")
    second.write_text("User: two", encoding="utf-8")
    store = SQLiteMemoryStore(config.store_path)
    store.initialize()
    queue = ReviewQueue(config.review_queue_path)

    summary = run_history_init(
        options=HistoryInitOptions(
            clients=(),
            include_generic=(first, second),
            review_only=True,
            auto_write_low_risk=False,
            limit=None,
            dry_run=False,
        ),
        config=config,
        source_home=tmp_path,
        store=store,
        queue=queue,
        extractor=FailingExtractor(),
    )

    assert summary.sources_processed == 2
    assert summary.transcripts_archived == 2
    assert summary.candidates_extracted == 0
    assert len(summary.errors) == 2
    assert all("bad extractor output" in error for error in summary.errors)
```

- [ ] **Step 2: Run focused tests and verify they fail**

Run:

```bash
py -m pytest tests/unit/test_history_initializer.py -v
```

Expected: FAIL because `run_history_init()` does not normalize, extract, or queue candidates yet.

- [ ] **Step 3: Implement normalization, extraction, validation, and review-only queueing**

In `src/ai_memory/history/initializer.py`, add imports near the top:

```python
from ai_memory.extraction.validator import validate_candidate
```

Replace the body of the `for source in sources:` loop inside `run_history_init()` with:

```python
    candidates_extracted = 0
    queued = 0
    auto_written = 0
    discarded = 0
    for source in sources:
        try:
            archive_path = _archive_source(config.raw_dir, source)
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
                    store.create_memory(
                        candidate,
                        status="auto_approved",
                        change_reason=f"historical import auto-write from {source.client}",
                    )
                    auto_written += 1
            archive_path.exists()
        except (OSError, UnicodeDecodeError) as exc:
            skipped += 1
            errors.append(f"{source.client}: {source.path}: {exc}")
        except Exception as exc:
            errors.append(f"{source.client}: {source.path}: {exc}")
```

Then update the `return HistoryInitSummary(...)` call at the end of `run_history_init()` to include the new counts:

```python
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
```

Add this helper below `_adapter_for()`:

```python

def _normalize_source(source: HistorySource) -> NormalizedTranscript:
    if source.client == "generic":
        return GenericTranscriptAdapter().normalize(source.path)
    return _adapter_for(source.client, source.path.parent).normalize(source.path)
```

- [ ] **Step 4: Run focused tests and verify they pass**

Run:

```bash
py -m pytest tests/unit/test_history_initializer.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

Run:

```bash
git add src/ai_memory/history/initializer.py tests/unit/test_history_initializer.py
git commit -m "feat: queue historical memory candidates for review"
```

---

### Task 4: Add Policy-Based Low-Risk Auto-Write Mode

**Files:**
- Modify: `src/ai_memory/history/initializer.py`
- Modify: `tests/unit/test_history_initializer.py`

- [ ] **Step 1: Add failing tests for `--auto-write-low-risk` routing**

Append this test to `tests/unit/test_history_initializer.py`:

```python

def high_impact_candidate() -> MemoryCandidate:
    return MemoryCandidate(
        uri="project://local/demo/testing",
        type="testing_rule",
        scope="project",
        content="All tests must use pytest.",
        summary="Tests use pytest.",
        confidence=0.9,
        risk="low",
        evidence="historical transcript stated testing rule",
    )


def test_history_init_auto_write_low_risk_uses_existing_policy(tmp_path: Path):
    home = tmp_path / ".ai-memory"
    config = init_home(home)
    transcript = tmp_path / "chat.md"
    transcript.write_text("User: Use pytest", encoding="utf-8")
    store = SQLiteMemoryStore(config.store_path)
    store.initialize()
    queue = ReviewQueue(config.review_queue_path)

    summary = run_history_init(
        options=HistoryInitOptions(
            clients=(),
            include_generic=(transcript,),
            review_only=False,
            auto_write_low_risk=True,
            limit=None,
            dry_run=False,
        ),
        config=config,
        source_home=tmp_path,
        store=store,
        queue=queue,
        extractor=StaticExtractor([low_risk_candidate(), high_impact_candidate()]),
    )

    assert summary.candidates_extracted == 2
    assert summary.auto_written == 1
    assert summary.review_queued == 1
    assert summary.discarded == 0
    assert len(store.search("pytest", limit=10)) == 1
    pending = queue.list_pending()
    assert len(pending) == 1
    assert pending[0].candidate.type == "testing_rule"
```

- [ ] **Step 2: Run focused tests and verify they fail**

Run:

```bash
py -m pytest tests/unit/test_history_initializer.py::test_history_init_auto_write_low_risk_uses_existing_policy -v
```

Expected: FAIL because non-review-only currently writes every valid candidate directly.

- [ ] **Step 3: Route non-review candidates through existing policy**

In `src/ai_memory/history/initializer.py`, add import:

```python
from ai_memory.core.policy import route_candidate
```

In the candidate loop inside `run_history_init()`, replace the current `else:` branch that directly calls `store.create_memory(...)` with:

```python
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
```

- [ ] **Step 4: Run focused tests and verify they pass**

Run:

```bash
py -m pytest tests/unit/test_history_initializer.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 4**

Run:

```bash
git add src/ai_memory/history/initializer.py tests/unit/test_history_initializer.py
git commit -m "feat: auto-write low-risk historical memories"
```

---

### Task 5: Wire `ai-memory history init` CLI and Summary Output

**Files:**
- Modify: `src/ai_memory/cli/main.py`
- Modify: `tests/unit/test_history_initializer.py`

- [ ] **Step 1: Add failing CLI tests**

Append these tests to `tests/unit/test_history_initializer.py`:

```python
from ai_memory.cli.main import run as cli_run


def test_cli_history_init_dry_run_outputs_summary(tmp_path: Path, capsys):
    home = tmp_path / ".ai-memory"
    source_home = tmp_path / "source-home"
    projects = source_home / ".claude" / "projects" / "demo"
    projects.mkdir(parents=True)
    (projects / "session.jsonl").write_text('{"type":"user","message":"Use pytest"}\n', encoding="utf-8")

    result = cli_run([
        "history",
        "init",
        "--home",
        str(home),
        "--source-home",
        str(source_home),
        "--clients",
        "claude-code",
        "--dry-run",
    ])

    output = capsys.readouterr().out
    assert result == 0
    assert "Historical initialization complete." in output
    assert "Clients scanned: 1" in output
    assert "Sources found: 1" in output
    assert "Dry run only. No archives, review items, or memories were written." in output
    assert not (home / "raw" / "claude-code").exists()


def test_cli_history_init_rejects_invalid_client(tmp_path: Path, capsys):
    result = cli_run(["history", "init", "--home", str(tmp_path / ".ai-memory"), "--clients", "unknown"])

    output = capsys.readouterr().err
    assert result == 2
    assert "Unsupported history client: unknown" in output


def test_cli_history_init_rejects_conflicting_modes(tmp_path: Path, capsys):
    result = cli_run([
        "history",
        "init",
        "--home",
        str(tmp_path / ".ai-memory"),
        "--review-only",
        "--auto-write-low-risk",
    ])

    output = capsys.readouterr().err
    assert result == 2
    assert "mutually exclusive" in output
```

- [ ] **Step 2: Run CLI tests and verify they fail**

Run:

```bash
py -m pytest tests/unit/test_history_initializer.py::test_cli_history_init_dry_run_outputs_summary tests/unit/test_history_initializer.py::test_cli_history_init_rejects_invalid_client tests/unit/test_history_initializer.py::test_cli_history_init_rejects_conflicting_modes -v
```

Expected: FAIL because `history` subcommand does not exist.

- [ ] **Step 3: Add parser support in `src/ai_memory/cli/main.py`**

In `build_parser()`, after the existing import parser block and before the MCP parser block, add:

```python
    history_parser = subparsers.add_parser("history", help="Historical transcript initialization")
    history_subparsers = history_parser.add_subparsers(dest="history_command", required=True)
    history_init = history_subparsers.add_parser("init", help="Initialize memories from historical transcripts")
    history_init.add_argument("--home", type=Path, default=Path.home() / ".ai-memory")
    history_init.add_argument("--source-home", type=Path, default=Path.home())
    history_init.add_argument("--clients", default="all")
    history_init.add_argument("--review-only", action="store_true")
    history_init.add_argument("--auto-write-low-risk", action="store_true")
    history_init.add_argument("--limit", type=int)
    history_init.add_argument("--dry-run", action="store_true")
    history_init.add_argument("--include-generic", type=Path, action="append", default=[])
```

- [ ] **Step 4: Add CLI execution branch in `run()`**

In `src/ai_memory/cli/main.py`, before the `if args.command == "mcp" ...` branch, add:

```python
    if args.command == "history" and args.history_command == "init":
        from ai_memory.extraction.providers.command import CommandExtractorProvider
        from ai_memory.history.initializer import HistoryInitOptions, parse_clients, run_history_init

        try:
            clients = parse_clients(args.clients)
            review_only = args.review_only or not args.auto_write_low_risk
            options = HistoryInitOptions(
                clients=clients,
                include_generic=tuple(args.include_generic),
                review_only=review_only,
                auto_write_low_risk=args.auto_write_low_risk,
                limit=args.limit,
                dry_run=args.dry_run,
            )
        except ValueError as error:
            parser.error(str(error))

        store, config = _init_store(args.home)
        queue = ReviewQueue(config.review_queue_path)
        extractor = None
        if config.extractor_provider == "command" and config.extractor_command:
            extractor = CommandExtractorProvider(config.extractor_command)
        summary = run_history_init(
            options=options,
            config=config,
            source_home=args.source_home,
            store=store,
            queue=queue,
            extractor=extractor,
        )
        _print_history_summary(summary, config.raw_dir, args.dry_run)
        return 0
```

At the bottom of the file, before `def main()`, add:

```python

def _print_history_summary(summary: object, raw_dir: Path, dry_run: bool) -> None:
    print("Historical initialization complete.")
    print()
    print(f"Clients scanned: {summary.clients_scanned}")
    print(f"Sources found: {summary.sources_found}")
    print(f"Sources processed: {summary.sources_processed}")
    print(f"Transcripts archived: {summary.transcripts_archived}")
    print(f"Transcripts skipped: {summary.transcripts_skipped}")
    print(f"Extraction skipped: {summary.extraction_skipped}")
    print(f"Candidates extracted: {summary.candidates_extracted}")
    print(f"Review queued: {summary.review_queued}")
    print(f"Auto-written: {summary.auto_written}")
    print(f"Discarded: {summary.discarded}")
    print(f"Errors: {len(summary.errors)}")
    print()
    if dry_run:
        print("Dry run only. No archives, review items, or memories were written.")
    else:
        print(f"Raw transcripts were archived under: {raw_dir}")
        print("Raw archives may contain original private content.")
        print("Review candidates with: ai-memory review")
    for error in summary.errors:
        print(f"Error: {error}")
```

- [ ] **Step 5: Run CLI tests and verify they pass**

Run:

```bash
py -m pytest tests/unit/test_history_initializer.py -v
```

Expected: PASS.

- [ ] **Step 6: Run existing CLI-adjacent tests**

Run:

```bash
py -m pytest tests/unit/test_adapters.py tests/unit/test_extraction.py tests/unit/test_privacy_review.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit Task 5**

Run:

```bash
git add src/ai_memory/cli/main.py tests/unit/test_history_initializer.py
git commit -m "feat: add history init CLI"
```

---

### Task 6: Update English and Chinese Documentation

**Files:**
- Modify: `README.md`
- Modify: `README_CN.md`

- [ ] **Step 1: Add English README section**

In `README.md`, add a section after the existing transcript import section:

```markdown
## Historical initialization

To initialize memory from previous AI-tool transcripts, run:

```bash
ai-memory history init --clients all --review-only
```

This scans supported local clients (`claude-code`, `codex-cli`, and `gemini-cli`), archives discovered transcripts under `~/.ai-memory/raw/<client>/`, and extracts candidate memories when an extractor provider is configured.

The default is review-only: valid candidates are queued for review instead of being written directly to durable memory.

```bash
ai-memory review
ai-memory approve <review_id>
ai-memory reject <review_id>
```

Preview without writing anything:

```bash
ai-memory history init --clients all --dry-run
```

Allow low-risk, high-confidence candidates to be written automatically while high-impact candidates still go to review:

```bash
ai-memory history init --clients all --auto-write-low-risk
```

Include generic transcript files or directories:

```bash
ai-memory history init --include-generic ./old-chats --review-only
```

Privacy note: raw archives may contain the original transcript text. Redaction and validation protect extracted durable memories, but raw archives are local copies of source transcripts.
```

- [ ] **Step 2: Add Chinese README section**

In `README_CN.md`, add a matching section near the existing transcript import discussion:

```markdown
## 历史记忆初始化

如果要从过去使用过的 AI 编程工具中初始化记忆，可以运行：

```bash
ai-memory history init --clients all --review-only
```

该命令会扫描本机支持的工具历史记录（`claude-code`、`codex-cli`、`gemini-cli`），把发现的 transcript 归档到 `~/.ai-memory/raw/<client>/`，并在已配置 extractor provider 时提取候选记忆。

默认是 review-only：有效候选记忆只进入 review queue，不会直接写入长期记忆库。

```bash
ai-memory review
ai-memory approve <review_id>
ai-memory reject <review_id>
```

只预览、不写入任何文件或记忆：

```bash
ai-memory history init --clients all --dry-run
```

如果你希望低风险、高置信度的候选记忆自动写入，同时高影响记忆仍然进入 review queue，可以运行：

```bash
ai-memory history init --clients all --auto-write-low-risk
```

也可以额外导入 generic transcript 文件或目录：

```bash
ai-memory history init --include-generic ./old-chats --review-only
```

隐私提醒：raw archive 可能包含原始 transcript 文本。redaction 和 validation 主要保护被提取出来的长期记忆，raw archive 本身仍然是源 transcript 的本地副本。
```

- [ ] **Step 3: Verify documentation has no Markdown fence issues**

Run:

```bash
git diff --check -- README.md README_CN.md
```

Expected: no output and exit code 0.

- [ ] **Step 4: Commit Task 6**

Run:

```bash
git add README.md README_CN.md
git commit -m "docs: document historical initialization"
```

---

### Task 7: Final Validation

**Files:**
- No new files expected.
- Validate all changed files and full unit test suite.

- [ ] **Step 1: Run full unit tests**

Run:

```bash
py -m pytest tests/unit -v
```

Expected: all tests pass. Previous baseline was 74 passed; the count should increase after adding historical initialization tests.

- [ ] **Step 2: Run lint if available**

Run:

```bash
py -m ruff check src tests
```

Expected: PASS. If `ruff` is not installed in the environment, record that it was unavailable and do not fake success.

- [ ] **Step 3: Run CLI smoke tests**

Run:

```bash
py -m ai_memory.cli.main history init --home .tmp-ai-memory-history-smoke --source-home . --clients all --dry-run
py -m ai_memory.cli.main review --home .tmp-ai-memory-history-smoke
```

Expected first command includes:

```text
Historical initialization complete.
Dry run only. No archives, review items, or memories were written.
```

Expected second command includes:

```text
No pending review items
```

- [ ] **Step 4: Remove smoke-test temp directory**

Run:

```bash
python -c "import shutil; shutil.rmtree('.tmp-ai-memory-history-smoke', ignore_errors=True)"
```

Expected: directory removed if it exists.

- [ ] **Step 5: Check working tree**

Run:

```bash
git status --short
```

Expected: only intentional untracked files unrelated to this feature may remain. Do not add `.idea/`, `src/ai_memory.egg-info/`, or `uv.lock` unless explicitly requested.

- [ ] **Step 6: Commit any validation-only fixes if needed**

If tests or lint required fixes, commit only the changed feature files:

```bash
git add src/ai_memory/history src/ai_memory/cli/main.py tests/unit/test_history_initializer.py README.md README_CN.md
git commit -m "fix: validate historical initialization"
```

Expected: no commit is created if no files changed after prior task commits.

---

## Self-Review

Spec coverage:

- CLI command and options: Task 5.
- Safe review-only default: Tasks 3 and 5.
- Optional low-risk auto-write: Task 4.
- Discovery across built-in adapters and generic paths: Tasks 1 and 2.
- Raw archive behavior and duplicate archive names: Task 2.
- Missing extractor reporting: Tasks 2 and 5.
- Per-source resilience: Task 3.
- Documentation updates in English and Chinese: Task 6.
- Full validation: Task 7.

Placeholder scan: no TODO/TBD placeholders are present. Each code-changing step includes exact file paths, code snippets, commands, and expected results.

Type consistency: `HistoryInitOptions`, `HistoryInitSummary`, `HistorySource`, `parse_clients()`, `collect_generic_sources()`, `archive_target_for()`, and `run_history_init()` are named consistently across tasks.
