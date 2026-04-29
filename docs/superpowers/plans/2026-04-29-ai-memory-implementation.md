# AI Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first local-first Python MVP of `ai-memory`: SQLite memory core, CLI, review queue, privacy redaction, context retrieval, generic transcript capture/import, MCP tool surface, and initial Claude/Codex/Gemini adapters.

**Architecture:** The implementation uses a tool-agnostic core with adapters at the edge. SQLite is the authoritative store, JSONL is the review queue interchange format, CLI commands drive local workflows, and the MCP layer delegates to the same core services as the CLI.

**Tech Stack:** Python 3.11+, stdlib `argparse`, `sqlite3`, `dataclasses`, `json`, `pathlib`; dependencies `PyYAML` for config and `mcp` for MCP serving; `pytest` for tests.

---

## File Structure Map

Create these files unless a task says otherwise:

```text
pyproject.toml
AGENTS.md
src/ai_memory/__init__.py
src/ai_memory/cli/__init__.py
src/ai_memory/cli/main.py
src/ai_memory/core/__init__.py
src/ai_memory/core/config.py
src/ai_memory/core/models.py
src/ai_memory/core/policy.py
src/ai_memory/core/uri.py
src/ai_memory/store/__init__.py
src/ai_memory/store/sqlite.py
src/ai_memory/review/__init__.py
src/ai_memory/review/queue.py
src/ai_memory/privacy/__init__.py
src/ai_memory/privacy/redactor.py
src/ai_memory/privacy/sensitive_paths.py
src/ai_memory/retrieval/__init__.py
src/ai_memory/retrieval/environment.py
src/ai_memory/retrieval/ranking.py
src/ai_memory/retrieval/assembler.py
src/ai_memory/extraction/__init__.py
src/ai_memory/extraction/transcript.py
src/ai_memory/extraction/validator.py
src/ai_memory/extraction/router.py
src/ai_memory/extraction/providers/__init__.py
src/ai_memory/extraction/providers/base.py
src/ai_memory/extraction/providers/command.py
src/ai_memory/adapters/__init__.py
src/ai_memory/adapters/base.py
src/ai_memory/adapters/generic_transcript.py
src/ai_memory/adapters/claude_code.py
src/ai_memory/adapters/codex_cli.py
src/ai_memory/adapters/gemini_cli.py
src/ai_memory/mcp/__init__.py
src/ai_memory/mcp/tools.py
src/ai_memory/mcp/server.py
src/ai_memory/wrappers/__init__.py
src/ai_memory/wrappers/aiwrap.py
tests/conftest.py
tests/unit/test_config.py
tests/unit/test_uri_policy.py
tests/unit/test_store.py
tests/unit/test_privacy_review.py
tests/unit/test_retrieval.py
tests/unit/test_extraction.py
tests/unit/test_adapters.py
tests/unit/test_mcp_tools.py
tests/fixtures/transcripts/generic/simple-chat.md
```

Responsibility boundaries:

- `core/`: data models, URI parsing, config, write policy.
- `store/`: SQLite schema, CRUD, FTS indexing, source/version/session persistence.
- `review/`: JSONL review queue and approval/rejection helpers.
- `privacy/`: secret redaction and sensitive path detection.
- `retrieval/`: environment detection, ranking, context assembly.
- `extraction/`: transcript normalization, candidate validation, provider interface, routing.
- `adapters/`: tool-specific discovery and transcript normalization only.
- `cli/`: user command parsing and output.
- `mcp/`: MCP tools delegating to core/store/retrieval logic.
- `wrappers/`: generic wrapper entry point for non-MCP CLI tools.

---

### Task 1: Bootstrap Python package and `ai-memory init`

**Files:**
- Create: `pyproject.toml`
- Create: `AGENTS.md`
- Create: `src/ai_memory/__init__.py`
- Create: `src/ai_memory/core/config.py`
- Create: `src/ai_memory/cli/__init__.py`
- Create: `src/ai_memory/cli/main.py`
- Create: `tests/conftest.py`
- Create: `tests/unit/test_config.py`

- [ ] **Step 1: Write failing tests for default path resolution and init command**

Create `tests/unit/test_config.py`:

```python
from pathlib import Path

from ai_memory.core.config import AppConfig, default_config, init_home
from ai_memory.cli.main import run


def test_default_config_uses_home_directory(tmp_path: Path):
    config = default_config(tmp_path)

    assert config.home == tmp_path / ".ai-memory"
    assert config.store_path == tmp_path / ".ai-memory" / "memory.db"
    assert config.raw_dir == tmp_path / ".ai-memory" / "raw"
    assert config.log_dir == tmp_path / ".ai-memory" / "logs"
    assert config.review_queue_path == tmp_path / ".ai-memory" / "review-queue.jsonl"
    assert config.extractor_provider is None


def test_init_home_creates_expected_files(tmp_path: Path):
    config = init_home(tmp_path)

    assert config.home.is_dir()
    assert config.raw_dir.is_dir()
    assert config.log_dir.is_dir()
    assert config.review_queue_path.exists()
    assert config.review_queue_path.read_text(encoding="utf-8") == ""
    assert (config.home / "config.yaml").exists()


def test_cli_init_accepts_custom_home(tmp_path: Path, capsys):
    exit_code = run(["init", "--home", str(tmp_path / "custom-memory")])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Initialized ai-memory" in captured.out
    assert (tmp_path / "custom-memory" / "config.yaml").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/unit/test_config.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'ai_memory'` or an import error for `ai_memory.core.config`.

- [ ] **Step 3: Create package metadata**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=69", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "ai-memory"
version = "0.1.0"
description = "Local-first multi-tool memory for AI coding agents"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
  "PyYAML>=6.0.1",
  "mcp>=1.2.0"
]

[project.optional-dependencies]
dev = [
  "pytest>=8.0.0"
]

[project.scripts]
ai-memory = "ai_memory.cli.main:main"
aiwrap = "ai_memory.wrappers.aiwrap:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

Create `AGENTS.md`:

```markdown
# AI Agent Instructions

- Keep changes small and directly tied to the current task.
- Prefer the Python standard library unless a dependency is already in `pyproject.toml`.
- Use tests before implementation for behavior changes.
- Do not store secrets, tokens, private keys, or `.env` values in fixtures.
- Run the most specific pytest target before marking a task complete.
```

Create `src/ai_memory/__init__.py`:

```python
__all__ = ["__version__"]

__version__ = "0.1.0"
```

Create `tests/conftest.py`:

```python
from pathlib import Path

import pytest


@pytest.fixture
def memory_home(tmp_path: Path) -> Path:
    return tmp_path / ".ai-memory"
```

- [ ] **Step 4: Implement config and CLI init**

Create `src/ai_memory/core/config.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class AppConfig:
    home: Path
    store_path: Path
    raw_dir: Path
    log_dir: Path
    review_queue_path: Path
    extractor_provider: str | None
    extractor_command: str | None
    max_input_chars: int
    retrieval_max_items: int
    retrieval_max_chars: int
    auto_write_confidence: float
    redact_secrets: bool
    confirm_sensitive_sources: bool


def default_config(user_home: Path | None = None) -> AppConfig:
    base_home = user_home if user_home is not None else Path.home()
    memory_home = base_home if base_home.name == ".ai-memory" else base_home / ".ai-memory"
    return AppConfig(
        home=memory_home,
        store_path=memory_home / "memory.db",
        raw_dir=memory_home / "raw",
        log_dir=memory_home / "logs",
        review_queue_path=memory_home / "review-queue.jsonl",
        extractor_provider=None,
        extractor_command=None,
        max_input_chars=60000,
        retrieval_max_items=12,
        retrieval_max_chars=6000,
        auto_write_confidence=0.85,
        redact_secrets=True,
        confirm_sensitive_sources=True,
    )


def config_to_dict(config: AppConfig) -> dict[str, Any]:
    return {
        "store": {"type": "sqlite", "path": str(config.store_path)},
        "paths": {
            "raw_dir": str(config.raw_dir),
            "log_dir": str(config.log_dir),
            "review_queue": str(config.review_queue_path),
        },
        "extractor": {
            "provider": config.extractor_provider,
            "command": config.extractor_command,
            "max_input_chars": config.max_input_chars,
        },
        "retrieval": {
            "max_items": config.retrieval_max_items,
            "max_chars": config.retrieval_max_chars,
        },
        "policy": {"auto_write_confidence": config.auto_write_confidence},
        "privacy": {
            "redact_secrets": config.redact_secrets,
            "confirm_sensitive_sources": config.confirm_sensitive_sources,
        },
        "clients": {
            "claude-code": {"enabled": True},
            "codex-cli": {"enabled": True},
            "gemini-cli": {"enabled": True},
        },
    }


def init_home(home: Path) -> AppConfig:
    config = default_config(home)
    config.home.mkdir(parents=True, exist_ok=True)
    config.raw_dir.mkdir(parents=True, exist_ok=True)
    config.log_dir.mkdir(parents=True, exist_ok=True)
    config.review_queue_path.touch(exist_ok=True)
    config_file = config.home / "config.yaml"
    config_file.write_text(yaml.safe_dump(config_to_dict(config), sort_keys=False), encoding="utf-8")
    return config
```

Create `src/ai_memory/cli/__init__.py`:

```python
__all__ = []
```

Create `src/ai_memory/cli/main.py`:

```python
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from ai_memory.core.config import init_home


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-memory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize local ai-memory storage")
    init_parser.add_argument("--home", type=Path, default=Path.home() / ".ai-memory")

    return parser


def run(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        config = init_home(args.home)
        print(f"Initialized ai-memory at {config.home}")
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


def main() -> None:
    raise SystemExit(run())
```

- [ ] **Step 5: Run test to verify it passes**

Run:

```bash
pytest tests/unit/test_config.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml AGENTS.md src/ai_memory tests/conftest.py tests/unit/test_config.py
git commit -m "feat: bootstrap ai-memory package"
```

---

### Task 2: Add core models, URI parsing, and write policy

**Files:**
- Create: `src/ai_memory/core/models.py`
- Create: `src/ai_memory/core/uri.py`
- Create: `src/ai_memory/core/policy.py`
- Create: `tests/unit/test_uri_policy.py`

- [ ] **Step 1: Write failing tests for URI validation and policy routing**

Create `tests/unit/test_uri_policy.py`:

```python
from ai_memory.core.models import MemoryCandidate
from ai_memory.core.policy import route_candidate
from ai_memory.core.uri import ParsedMemoryUri, parse_memory_uri


def test_parse_project_uri():
    parsed = parse_memory_uri("project://github.com/acme/app/testing")

    assert parsed == ParsedMemoryUri(
        namespace="project",
        authority="github.com",
        parts=("acme", "app", "testing"),
    )


def test_reject_invalid_namespace():
    try:
        parse_memory_uri("unknown://github.com/acme/app/testing")
    except ValueError as exc:
        assert "Unsupported memory namespace" in str(exc)
    else:
        raise AssertionError("invalid namespace should fail")


def test_low_risk_command_auto_approves():
    candidate = MemoryCandidate(
        uri="project://github.com/acme/app/commands",
        type="project_command",
        scope="project",
        content="Use pnpm test for tests.",
        summary="Test command is pnpm test.",
        confidence=0.91,
        risk="low",
        evidence="package.json scripts were checked",
        tags=("testing",),
        triggers=("pnpm", "test"),
        repo_id="github.com/acme/app",
    )

    decision = route_candidate(candidate, auto_write_confidence=0.85)

    assert decision.action == "auto_write"
    assert decision.reason == "low-risk high-confidence candidate"


def test_testing_rule_requires_review_even_when_confident():
    candidate = MemoryCandidate(
        uri="project://github.com/acme/app/testing",
        type="testing_rule",
        scope="project",
        content="Use pnpm test for tests.",
        summary="Test command is pnpm test.",
        confidence=0.95,
        risk="low",
        evidence="user confirmed testing policy",
        tags=("testing",),
        triggers=("pnpm", "test"),
        repo_id="github.com/acme/app",
    )

    decision = route_candidate(candidate, auto_write_confidence=0.85)

    assert decision.action == "review"
    assert decision.reason == "high-impact memory type requires review"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/unit/test_uri_policy.py -v
```

Expected: FAIL because `ai_memory.core.models`, `uri`, and `policy` do not exist.

- [ ] **Step 3: Implement models**

Create `src/ai_memory/core/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

MemoryStatus = Literal["proposed", "approved", "auto_approved", "rejected", "archived", "expired", "conflicted"]
RiskLevel = Literal["low", "medium", "high"]
RouteAction = Literal["auto_write", "review", "discard"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


@dataclass(frozen=True)
class MemoryCandidate:
    uri: str
    type: str
    scope: str
    content: str
    summary: str
    confidence: float
    risk: RiskLevel
    evidence: str
    tags: tuple[str, ...] = field(default_factory=tuple)
    triggers: tuple[str, ...] = field(default_factory=tuple)
    repo_id: str | None = None
    branch: str | None = None
    path_glob: str | None = None
    expires_at: str | None = None
    source_client: str | None = None
    session_id: str | None = None
    transcript_ref: str | None = None


@dataclass(frozen=True)
class MemoryRecord:
    id: str
    uri: str
    type: str
    scope: str
    content: str
    summary: str
    status: MemoryStatus
    confidence: float
    risk: RiskLevel
    repo_id: str | None
    branch: str | None
    path_glob: str | None
    expires_at: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class RouteDecision:
    action: RouteAction
    reason: str


@dataclass(frozen=True)
class NormalizedMessage:
    role: str
    content: str
    timestamp: str | None = None
    name: str | None = None


@dataclass(frozen=True)
class NormalizedTranscript:
    session_id: str
    client: str
    source_path: str
    messages: tuple[NormalizedMessage, ...]
    cwd: str | None = None
    repo_id: str | None = None
    branch: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
```

- [ ] **Step 4: Implement URI parsing**

Create `src/ai_memory/core/uri.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

SUPPORTED_NAMESPACES = {"global", "org", "project", "branch", "path", "tool", "system"}


@dataclass(frozen=True)
class ParsedMemoryUri:
    namespace: str
    authority: str
    parts: tuple[str, ...]


def parse_memory_uri(uri: str) -> ParsedMemoryUri:
    parsed = urlparse(uri)
    if parsed.scheme not in SUPPORTED_NAMESPACES:
        raise ValueError(f"Unsupported memory namespace: {parsed.scheme}")
    if not parsed.netloc and parsed.scheme != "system":
        raise ValueError(f"Memory URI requires an authority: {uri}")
    path_parts = tuple(part for part in parsed.path.split("/") if part)
    if parsed.scheme == "system" and parsed.netloc:
        path_parts = (parsed.netloc, *path_parts)
        authority = ""
    else:
        authority = parsed.netloc
    if not path_parts:
        raise ValueError(f"Memory URI requires a path: {uri}")
    return ParsedMemoryUri(namespace=parsed.scheme, authority=authority, parts=path_parts)


def validate_memory_uri(uri: str) -> None:
    parse_memory_uri(uri)
```

- [ ] **Step 5: Implement write policy**

Create `src/ai_memory/core/policy.py`:

```python
from __future__ import annotations

from ai_memory.core.models import MemoryCandidate, RouteDecision

AUTO_WRITE_TYPES = {
    "project_command",
    "branch_state",
    "task_todo",
    "dependency_note",
    "tool_note",
    "pitfall",
}

HIGH_IMPACT_TYPES = {
    "user_preference",
    "workflow_rule",
    "architecture_decision",
    "api_contract",
    "security_constraint",
    "coding_style",
    "testing_rule",
}


def route_candidate(candidate: MemoryCandidate, auto_write_confidence: float) -> RouteDecision:
    if candidate.confidence < 0.5:
        return RouteDecision(action="discard", reason="candidate confidence is too low")
    if candidate.type in HIGH_IMPACT_TYPES:
        return RouteDecision(action="review", reason="high-impact memory type requires review")
    if candidate.risk != "low":
        return RouteDecision(action="review", reason="non-low risk candidate requires review")
    if candidate.confidence < auto_write_confidence:
        return RouteDecision(action="review", reason="candidate confidence is below auto-write threshold")
    if candidate.type not in AUTO_WRITE_TYPES:
        return RouteDecision(action="review", reason="memory type is not auto-writeable")
    return RouteDecision(action="auto_write", reason="low-risk high-confidence candidate")
```

- [ ] **Step 6: Run test to verify it passes**

Run:

```bash
pytest tests/unit/test_uri_policy.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/ai_memory/core tests/unit/test_uri_policy.py
git commit -m "feat: add memory models and routing policy"
```

---

### Task 3: Implement SQLite store, schema, versions, sources, and FTS search

**Files:**
- Create: `src/ai_memory/store/__init__.py`
- Create: `src/ai_memory/store/sqlite.py`
- Create: `tests/unit/test_store.py`

- [ ] **Step 1: Write failing SQLite store tests**

Create `tests/unit/test_store.py`:

```python
from pathlib import Path

from ai_memory.core.models import MemoryCandidate
from ai_memory.store.sqlite import SQLiteMemoryStore


def make_candidate() -> MemoryCandidate:
    return MemoryCandidate(
        uri="project://github.com/acme/app/commands",
        type="project_command",
        scope="project",
        content="Use pnpm test for tests.",
        summary="Test command is pnpm test.",
        confidence=0.91,
        risk="low",
        evidence="package.json scripts were checked",
        tags=("testing", "pnpm"),
        triggers=("test", "pnpm"),
        repo_id="github.com/acme/app",
        source_client="generic",
        session_id="sess_test",
        transcript_ref="raw/generic/sess_test.md",
    )


def test_create_memory_persists_record_source_version_and_fts(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()

    record = store.create_memory(make_candidate(), status="auto_approved", change_reason="test insert")

    loaded = store.get_memory(record.id)
    assert loaded is not None
    assert loaded.content == "Use pnpm test for tests."
    assert loaded.status == "auto_approved"

    sources = store.list_sources(record.id)
    assert len(sources) == 1
    assert sources[0]["evidence"] == "package.json scripts were checked"

    versions = store.list_versions(record.id)
    assert len(versions) == 1
    assert versions[0]["version"] == 1

    results = store.search("pnpm", limit=5)
    assert [item.id for item in results] == [record.id]


def test_update_memory_creates_new_version(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()
    record = store.create_memory(make_candidate(), status="auto_approved", change_reason="test insert")

    updated = store.update_memory(record.id, "Use pnpm test -- --runInBand for tests.", "command refined")

    assert updated.content == "Use pnpm test -- --runInBand for tests."
    versions = store.list_versions(record.id)
    assert [version["version"] for version in versions] == [1, 2]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/unit/test_store.py -v
```

Expected: FAIL because `ai_memory.store.sqlite` does not exist.

- [ ] **Step 3: Implement SQLite store**

Create `src/ai_memory/store/__init__.py`:

```python
__all__ = ["SQLiteMemoryStore"]

from ai_memory.store.sqlite import SQLiteMemoryStore
```

Create `src/ai_memory/store/sqlite.py`:

```python
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Literal

from ai_memory.core.models import MemoryCandidate, MemoryRecord, MemoryStatus, new_id, utc_now_iso


class SQLiteMemoryStore:
    def __init__(self, path: Path):
        self.path = path

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    uri TEXT NOT NULL,
                    type TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    content TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    status TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    risk TEXT NOT NULL,
                    repo_id TEXT,
                    branch TEXT,
                    path_glob TEXT,
                    expires_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS memory_sources (
                    id TEXT PRIMARY KEY,
                    memory_id TEXT NOT NULL,
                    client TEXT,
                    session_id TEXT,
                    transcript_ref TEXT,
                    evidence TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS memory_versions (
                    id TEXT PRIMARY KEY,
                    memory_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    status TEXT NOT NULL,
                    changed_by TEXT NOT NULL,
                    change_reason TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS memory_tags (
                    memory_id TEXT NOT NULL,
                    tag TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS memory_triggers (
                    memory_id TEXT NOT NULL,
                    trigger TEXT NOT NULL
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                    memory_id UNINDEXED,
                    uri,
                    content,
                    summary,
                    tags,
                    triggers
                );
                """
            )

    def create_memory(
        self,
        candidate: MemoryCandidate,
        status: MemoryStatus,
        change_reason: str,
    ) -> MemoryRecord:
        now = utc_now_iso()
        memory_id = new_id("mem")
        record = MemoryRecord(
            id=memory_id,
            uri=candidate.uri,
            type=candidate.type,
            scope=candidate.scope,
            content=candidate.content,
            summary=candidate.summary,
            status=status,
            confidence=candidate.confidence,
            risk=candidate.risk,
            repo_id=candidate.repo_id,
            branch=candidate.branch,
            path_glob=candidate.path_glob,
            expires_at=candidate.expires_at,
            created_at=now,
            updated_at=now,
        )
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO memories VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.uri,
                    record.type,
                    record.scope,
                    record.content,
                    record.summary,
                    record.status,
                    record.confidence,
                    record.risk,
                    record.repo_id,
                    record.branch,
                    record.path_glob,
                    record.expires_at,
                    record.created_at,
                    record.updated_at,
                ),
            )
            db.execute(
                "INSERT INTO memory_sources VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    new_id("src"),
                    memory_id,
                    candidate.source_client,
                    candidate.session_id,
                    candidate.transcript_ref,
                    candidate.evidence,
                    now,
                ),
            )
            db.execute(
                "INSERT INTO memory_versions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (new_id("ver"), memory_id, 1, record.content, record.summary, record.status, "ai-memory", change_reason, now),
            )
            self._replace_tags(db, memory_id, candidate.tags)
            self._replace_triggers(db, memory_id, candidate.triggers)
            self._replace_fts(db, record, candidate.tags, candidate.triggers)
        return record

    def get_memory(self, memory_id: str) -> MemoryRecord | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
        return self._record_from_row(row) if row else None

    def update_memory(self, memory_id: str, content: str, change_reason: str) -> MemoryRecord:
        existing = self.get_memory(memory_id)
        if existing is None:
            raise ValueError(f"Unknown memory id: {memory_id}")
        now = utc_now_iso()
        with self.connect() as db:
            current_version = db.execute(
                "SELECT COALESCE(MAX(version), 0) FROM memory_versions WHERE memory_id = ?",
                (memory_id,),
            ).fetchone()[0]
            db.execute("UPDATE memories SET content = ?, updated_at = ? WHERE id = ?", (content, now, memory_id))
            db.execute(
                "INSERT INTO memory_versions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_id("ver"),
                    memory_id,
                    current_version + 1,
                    content,
                    existing.summary,
                    existing.status,
                    "ai-memory",
                    change_reason,
                    now,
                ),
            )
            updated = self.get_memory(memory_id)
            if updated is None:
                raise ValueError(f"Memory disappeared during update: {memory_id}")
            tags = [row["tag"] for row in db.execute("SELECT tag FROM memory_tags WHERE memory_id = ?", (memory_id,))]
            triggers = [row["trigger"] for row in db.execute("SELECT trigger FROM memory_triggers WHERE memory_id = ?", (memory_id,))]
            self._replace_fts(db, updated, tags, triggers)
        refreshed = self.get_memory(memory_id)
        if refreshed is None:
            raise ValueError(f"Memory disappeared after update: {memory_id}")
        return refreshed

    def search(self, query: str, limit: int) -> list[MemoryRecord]:
        with self.connect() as db:
            rows = db.execute(
                """
                SELECT memories.*
                FROM memory_fts
                JOIN memories ON memories.id = memory_fts.memory_id
                WHERE memory_fts MATCH ?
                  AND memories.status IN ('approved', 'auto_approved')
                LIMIT ?
                """,
                (query, limit),
            ).fetchall()
        return [self._record_from_row(row) for row in rows]

    def list_sources(self, memory_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM memory_sources WHERE memory_id = ?", (memory_id,)).fetchall()
        return [dict(row) for row in rows]

    def list_versions(self, memory_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM memory_versions WHERE memory_id = ? ORDER BY version", (memory_id,)).fetchall()
        return [dict(row) for row in rows]

    def _replace_tags(self, db: sqlite3.Connection, memory_id: str, tags: tuple[str, ...]) -> None:
        db.execute("DELETE FROM memory_tags WHERE memory_id = ?", (memory_id,))
        db.executemany("INSERT INTO memory_tags VALUES (?, ?)", [(memory_id, tag) for tag in tags])

    def _replace_triggers(self, db: sqlite3.Connection, memory_id: str, triggers: tuple[str, ...]) -> None:
        db.execute("DELETE FROM memory_triggers WHERE memory_id = ?", (memory_id,))
        db.executemany("INSERT INTO memory_triggers VALUES (?, ?)", [(memory_id, trigger) for trigger in triggers])

    def _replace_fts(self, db: sqlite3.Connection, record: MemoryRecord, tags: list[str] | tuple[str, ...], triggers: list[str] | tuple[str, ...]) -> None:
        db.execute("DELETE FROM memory_fts WHERE memory_id = ?", (record.id,))
        db.execute(
            "INSERT INTO memory_fts VALUES (?, ?, ?, ?, ?, ?)",
            (record.id, record.uri, record.content, record.summary, " ".join(tags), " ".join(triggers)),
        )

    def _record_from_row(self, row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            id=row["id"],
            uri=row["uri"],
            type=row["type"],
            scope=row["scope"],
            content=row["content"],
            summary=row["summary"],
            status=row["status"],
            confidence=row["confidence"],
            risk=row["risk"],
            repo_id=row["repo_id"],
            branch=row["branch"],
            path_glob=row["path_glob"],
            expires_at=row["expires_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
pytest tests/unit/test_store.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_memory/store tests/unit/test_store.py
git commit -m "feat: add sqlite memory store"
```

---

### Task 4: Add privacy redaction and JSONL review queue

**Files:**
- Create: `src/ai_memory/privacy/__init__.py`
- Create: `src/ai_memory/privacy/redactor.py`
- Create: `src/ai_memory/privacy/sensitive_paths.py`
- Create: `src/ai_memory/review/__init__.py`
- Create: `src/ai_memory/review/queue.py`
- Create: `tests/unit/test_privacy_review.py`

- [ ] **Step 1: Write failing privacy and review queue tests**

Create `tests/unit/test_privacy_review.py`:

```python
from pathlib import Path

from ai_memory.core.models import MemoryCandidate
from ai_memory.privacy.redactor import redact_secrets
from ai_memory.privacy.sensitive_paths import is_sensitive_path
from ai_memory.review.queue import ReviewQueue


def test_redact_common_secrets():
    text = "Authorization: Bearer abcdef1234567890\nDATABASE_URL=postgres://user:pass@example.com/db"

    redacted = redact_secrets(text)

    assert "abcdef1234567890" not in redacted
    assert "user:pass" not in redacted
    assert "[REDACTED:BEARER_TOKEN]" in redacted
    assert "postgres://user:[REDACTED]@example.com/db" in redacted


def test_detect_sensitive_paths():
    assert is_sensitive_path(Path(".env"))
    assert is_sensitive_path(Path("/home/user/.ssh/id_ed25519"))
    assert is_sensitive_path(Path("credentials.json"))
    assert not is_sensitive_path(Path("docs/notes.md"))


def test_review_queue_round_trip(tmp_path: Path):
    candidate = MemoryCandidate(
        uri="project://github.com/acme/app/testing",
        type="testing_rule",
        scope="project",
        content="Use pnpm test for tests.",
        summary="Test command is pnpm test.",
        confidence=0.93,
        risk="low",
        evidence="user confirmed",
    )
    queue = ReviewQueue(tmp_path / "review-queue.jsonl")

    item = queue.enqueue(candidate, reason="testing_rule requires review")
    pending = queue.list_pending()

    assert len(pending) == 1
    assert pending[0].id == item.id
    assert pending[0].candidate.type == "testing_rule"

    queue.mark(item.id, "approved")
    assert queue.list_pending() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/unit/test_privacy_review.py -v
```

Expected: FAIL because privacy and review modules do not exist.

- [ ] **Step 3: Implement privacy modules**

Create `src/ai_memory/privacy/__init__.py`:

```python
__all__ = ["redact_secrets", "is_sensitive_path"]

from ai_memory.privacy.redactor import redact_secrets
from ai_memory.privacy.sensitive_paths import is_sensitive_path
```

Create `src/ai_memory/privacy/redactor.py`:

```python
from __future__ import annotations

import re

BEARER_RE = re.compile(r"Bearer\s+[A-Za-z0-9._\-]+")
DATABASE_URL_RE = re.compile(r"(postgres(?:ql)?://[^:\s]+):([^@\s]+)@")
API_KEY_RE = re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)([^\s]+)")
PASSWORD_RE = re.compile(r"(?i)(password\s*[=:]\s*)([^\s]+)")
PRIVATE_KEY_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----")


def redact_secrets(text: str) -> str:
    redacted = BEARER_RE.sub("Bearer [REDACTED:BEARER_TOKEN]", text)
    redacted = DATABASE_URL_RE.sub(r"\1:[REDACTED]@", redacted)
    redacted = API_KEY_RE.sub(r"\1[REDACTED:API_KEY]", redacted)
    redacted = PASSWORD_RE.sub(r"\1[REDACTED:PASSWORD]", redacted)
    redacted = PRIVATE_KEY_RE.sub("[REDACTED:PRIVATE_KEY]", redacted)
    return redacted
```

Create `src/ai_memory/privacy/sensitive_paths.py`:

```python
from __future__ import annotations

from pathlib import Path

SENSITIVE_NAMES = {
    ".env",
    "id_rsa",
    "id_ed25519",
    "credentials.json",
    "application_default_credentials.json",
}

SENSITIVE_SUFFIXES = {".pem", ".key"}
SENSITIVE_PARTS = {".ssh", ".aws"}


def is_sensitive_path(path: Path) -> bool:
    name = path.name
    if name in SENSITIVE_NAMES:
        return True
    if name.startswith(".env."):
        return True
    if path.suffix in SENSITIVE_SUFFIXES:
        return True
    return any(part in SENSITIVE_PARTS for part in path.parts)
```

- [ ] **Step 4: Implement review queue**

Create `src/ai_memory/review/__init__.py`:

```python
__all__ = ["ReviewQueue", "ReviewItem"]

from ai_memory.review.queue import ReviewItem, ReviewQueue
```

Create `src/ai_memory/review/queue.py`:

```python
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from ai_memory.core.models import MemoryCandidate, new_id, utc_now_iso

ReviewStatus = Literal["pending", "approved", "rejected"]


@dataclass(frozen=True)
class ReviewItem:
    id: str
    candidate: MemoryCandidate
    reason: str
    status: ReviewStatus
    created_at: str
    reviewed_at: str | None = None


class ReviewQueue:
    def __init__(self, path: Path):
        self.path = path

    def enqueue(self, candidate: MemoryCandidate, reason: str) -> ReviewItem:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        item = ReviewItem(
            id=new_id("rev"),
            candidate=candidate,
            reason=reason,
            status="pending",
            created_at=utc_now_iso(),
        )
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(self._item_to_dict(item), ensure_ascii=False) + "\n")
        return item

    def list_pending(self) -> list[ReviewItem]:
        return [item for item in self._read_all() if item.status == "pending"]

    def mark(self, review_id: str, status: ReviewStatus) -> None:
        items = []
        found = False
        for item in self._read_all():
            if item.id == review_id:
                items.append(ReviewItem(item.id, item.candidate, item.reason, status, item.created_at, utc_now_iso()))
                found = True
            else:
                items.append(item)
        if not found:
            raise ValueError(f"Unknown review id: {review_id}")
        self._write_all(items)

    def _read_all(self) -> list[ReviewItem]:
        if not self.path.exists():
            return []
        items = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                items.append(self._item_from_dict(json.loads(line)))
        return items

    def _write_all(self, items: list[ReviewItem]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        content = "".join(json.dumps(self._item_to_dict(item), ensure_ascii=False) + "\n" for item in items)
        self.path.write_text(content, encoding="utf-8")

    def _item_to_dict(self, item: ReviewItem) -> dict[str, object]:
        data = asdict(item)
        data["candidate"] = asdict(item.candidate)
        return data

    def _item_from_dict(self, data: dict[str, object]) -> ReviewItem:
        candidate_data = data["candidate"]
        if not isinstance(candidate_data, dict):
            raise ValueError("review candidate must be an object")
        candidate_data["tags"] = tuple(candidate_data.get("tags", ()))
        candidate_data["triggers"] = tuple(candidate_data.get("triggers", ()))
        return ReviewItem(
            id=str(data["id"]),
            candidate=MemoryCandidate(**candidate_data),
            reason=str(data["reason"]),
            status=data["status"],
            created_at=str(data["created_at"]),
            reviewed_at=data.get("reviewed_at"),
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run:

```bash
pytest tests/unit/test_privacy_review.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ai_memory/privacy src/ai_memory/review tests/unit/test_privacy_review.py
git commit -m "feat: add privacy redaction and review queue"
```

---

### Task 5: Implement environment detection, ranking, context assembly, and basic CLI memory commands

**Files:**
- Create: `src/ai_memory/retrieval/__init__.py`
- Create: `src/ai_memory/retrieval/environment.py`
- Create: `src/ai_memory/retrieval/ranking.py`
- Create: `src/ai_memory/retrieval/assembler.py`
- Modify: `src/ai_memory/cli/main.py`
- Test: `tests/unit/test_retrieval.py`

- [ ] **Step 1: Write failing retrieval and CLI tests**

Create `tests/unit/test_retrieval.py`:

```python
from pathlib import Path

from ai_memory.core.models import MemoryCandidate
from ai_memory.retrieval.assembler import assemble_context, hook_json
from ai_memory.retrieval.environment import detect_environment
from ai_memory.store.sqlite import SQLiteMemoryStore
from ai_memory.cli.main import run


def test_detect_environment_without_git(tmp_path: Path):
    env = detect_environment(tmp_path, client="generic", prompt="run tests")

    assert env["cwd"] == str(tmp_path)
    assert env["client"] == "generic"
    assert env["prompt"] == "run tests"
    assert env["repo_id"].startswith("local/")


def test_assemble_context_groups_memories(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()
    record = store.create_memory(
        MemoryCandidate(
            uri="project://local/demo/commands",
            type="project_command",
            scope="project",
            content="Use pytest for tests.",
            summary="Test command is pytest.",
            confidence=0.9,
            risk="low",
            evidence="user confirmed",
            tags=("testing",),
            triggers=("pytest",),
            repo_id="local/demo",
        ),
        status="auto_approved",
        change_reason="test",
    )

    context = assemble_context([record], title="Retrieved Memory")

    assert "# Retrieved Memory" in context
    assert "project://local/demo/commands" in context
    assert "Use pytest for tests." in context


def test_hook_json_contains_additional_context():
    payload = hook_json("SessionStart", "# Retrieved Memory\n- Use pytest")

    assert payload["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "Use pytest" in payload["hookSpecificOutput"]["additionalContext"]


def test_cli_add_search_and_context(tmp_path: Path, capsys):
    home = tmp_path / ".ai-memory"
    assert run(["init", "--home", str(home)]) == 0
    assert run([
        "add",
        "project://local/demo/commands",
        "Use pytest for tests.",
        "--home",
        str(home),
        "--type",
        "project_command",
        "--scope",
        "project",
    ]) == 0
    assert run(["search", "pytest", "--home", str(home)]) == 0
    search_output = capsys.readouterr().out
    assert "Use pytest for tests." in search_output

    assert run(["context", "--home", str(home), "--prompt", "run tests"]) == 0
    context_output = capsys.readouterr().out
    assert "Use pytest for tests." in context_output
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/unit/test_retrieval.py -v
```

Expected: FAIL because retrieval modules and CLI commands do not exist.

- [ ] **Step 3: Implement retrieval modules**

Create `src/ai_memory/retrieval/__init__.py`:

```python
__all__ = []
```

Create `src/ai_memory/retrieval/environment.py`:

```python
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path


def detect_environment(cwd: Path, client: str, prompt: str | None = None) -> dict[str, str | None]:
    resolved = cwd.resolve()
    git_root = _git_value(resolved, ["git", "rev-parse", "--show-toplevel"])
    branch = _git_value(resolved, ["git", "branch", "--show-current"])
    remote = _git_value(resolved, ["git", "config", "--get", "remote.origin.url"])
    repo_id = _repo_id(remote) if remote else f"local/{hashlib.sha1(str(resolved).encode()).hexdigest()[:12]}"
    return {
        "cwd": str(resolved),
        "client": client,
        "prompt": prompt,
        "git_root": git_root,
        "branch": branch,
        "remote": remote,
        "repo_id": repo_id,
    }


def _git_value(cwd: Path, command: list[str]) -> str | None:
    try:
        result = subprocess.run(command, cwd=cwd, check=False, capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def _repo_id(remote: str) -> str:
    cleaned = remote.strip()
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]
    if cleaned.startswith("git@"):
        host, path = cleaned[4:].split(":", 1)
        return f"{host}/{path}"
    if "://" in cleaned:
        without_scheme = cleaned.split("://", 1)[1]
        return without_scheme
    return cleaned.replace("\\", "/")
```

Create `src/ai_memory/retrieval/ranking.py`:

```python
from __future__ import annotations

from ai_memory.core.models import MemoryRecord

STATUS_WEIGHT = {"approved": 50, "auto_approved": 30}
SCOPE_WEIGHT = {"branch": 100, "path": 80, "project": 70, "tool": 40, "global": 35, "org": 35, "system": 25}


def rank_records(records: list[MemoryRecord]) -> list[MemoryRecord]:
    return sorted(records, key=_score, reverse=True)


def _score(record: MemoryRecord) -> int:
    return STATUS_WEIGHT.get(record.status, -100) + SCOPE_WEIGHT.get(record.scope, 0) + int(record.confidence * 10)
```

Create `src/ai_memory/retrieval/assembler.py`:

```python
from __future__ import annotations

from ai_memory.core.models import MemoryRecord


def assemble_context(records: list[MemoryRecord], title: str = "Retrieved Memory") -> str:
    lines = [f"# {title}", ""]
    if not records:
        lines.append("No relevant approved memory found.")
        return "\n".join(lines)
    for record in records:
        lines.append(f"## {record.uri}")
        lines.append("")
        lines.append(f"- Type: {record.type}")
        lines.append(f"- Status: {record.status}")
        lines.append(f"- Memory: {record.content}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def hook_json(event: str, context: str) -> dict[str, dict[str, str]]:
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": context}}
```

- [ ] **Step 4: Extend CLI with add, search, and context**

Modify `src/ai_memory/cli/main.py` so the full file is:

```python
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from ai_memory.core.config import init_home
from ai_memory.core.models import MemoryCandidate
from ai_memory.retrieval.assembler import assemble_context, hook_json
from ai_memory.retrieval.ranking import rank_records
from ai_memory.store.sqlite import SQLiteMemoryStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-memory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize local ai-memory storage")
    init_parser.add_argument("--home", type=Path, default=Path.home() / ".ai-memory")

    add_parser = subparsers.add_parser("add", help="Add an approved memory")
    add_parser.add_argument("uri")
    add_parser.add_argument("content")
    add_parser.add_argument("--home", type=Path, default=Path.home() / ".ai-memory")
    add_parser.add_argument("--type", default="project_command")
    add_parser.add_argument("--scope", default="project")

    search_parser = subparsers.add_parser("search", help="Search approved memories")
    search_parser.add_argument("query")
    search_parser.add_argument("--home", type=Path, default=Path.home() / ".ai-memory")
    search_parser.add_argument("--limit", type=int, default=10)

    context_parser = subparsers.add_parser("context", help="Build retrieved memory context")
    context_parser.add_argument("--home", type=Path, default=Path.home() / ".ai-memory")
    context_parser.add_argument("--prompt", default="memory")
    context_parser.add_argument("--format", choices=("markdown", "hook-json"), default="markdown")
    context_parser.add_argument("--event", default="SessionStart")

    return parser


def run(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        config = init_home(args.home)
        SQLiteMemoryStore(config.store_path).initialize()
        print(f"Initialized ai-memory at {config.home}")
        return 0

    if args.command == "add":
        store = SQLiteMemoryStore(args.home / "memory.db")
        store.initialize()
        candidate = MemoryCandidate(
            uri=args.uri,
            type=args.type,
            scope=args.scope,
            content=args.content,
            summary=args.content,
            confidence=1.0,
            risk="low",
            evidence="manual CLI add",
            tags=tuple(args.content.lower().split()),
            triggers=tuple(args.content.lower().split()),
        )
        record = store.create_memory(candidate, status="approved", change_reason="manual CLI add")
        print(f"Added memory {record.id}")
        return 0

    if args.command == "search":
        store = SQLiteMemoryStore(args.home / "memory.db")
        store.initialize()
        records = store.search(args.query, args.limit)
        for record in records:
            print(f"{record.id} {record.uri} {record.content}")
        return 0

    if args.command == "context":
        store = SQLiteMemoryStore(args.home / "memory.db")
        store.initialize()
        records = rank_records(store.search(args.prompt, limit=12))
        context = assemble_context(records)
        if args.format == "hook-json":
            print(json.dumps(hook_json(args.event, context), ensure_ascii=False))
        else:
            print(context)
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


def main() -> None:
    raise SystemExit(run())
```

- [ ] **Step 5: Run retrieval tests**

Run:

```bash
pytest tests/unit/test_retrieval.py -v
```

Expected: PASS.

- [ ] **Step 6: Run earlier tests to catch regressions**

Run:

```bash
pytest tests/unit/test_config.py tests/unit/test_store.py tests/unit/test_uri_policy.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/ai_memory/retrieval src/ai_memory/cli/main.py tests/unit/test_retrieval.py
git commit -m "feat: add memory retrieval context commands"
```

---

### Task 6: Implement generic transcript import, redaction, extractor provider interface, validation, and capture routing

**Files:**
- Create: `src/ai_memory/extraction/__init__.py`
- Create: `src/ai_memory/extraction/transcript.py`
- Create: `src/ai_memory/extraction/validator.py`
- Create: `src/ai_memory/extraction/router.py`
- Create: `src/ai_memory/extraction/providers/__init__.py`
- Create: `src/ai_memory/extraction/providers/base.py`
- Create: `src/ai_memory/extraction/providers/command.py`
- Create: `src/ai_memory/adapters/__init__.py`
- Create: `src/ai_memory/adapters/base.py`
- Create: `src/ai_memory/adapters/generic_transcript.py`
- Modify: `src/ai_memory/cli/main.py`
- Create: `tests/fixtures/transcripts/generic/simple-chat.md`
- Create: `tests/unit/test_extraction.py`

- [ ] **Step 1: Write transcript fixture**

Create `tests/fixtures/transcripts/generic/simple-chat.md`:

```markdown
# Chat

User: In this project, use pytest for tests.

Assistant: Understood. I will use pytest for test runs.
```

- [ ] **Step 2: Write failing extraction tests**

Create `tests/unit/test_extraction.py`:

```python
from pathlib import Path

from ai_memory.adapters.generic_transcript import GenericTranscriptAdapter
from ai_memory.core.models import MemoryCandidate
from ai_memory.extraction.router import route_candidates
from ai_memory.extraction.validator import validate_candidate
from ai_memory.review.queue import ReviewQueue
from ai_memory.store.sqlite import SQLiteMemoryStore


def test_generic_markdown_transcript_normalizes_fixture():
    adapter = GenericTranscriptAdapter()
    transcript = adapter.normalize(Path("tests/fixtures/transcripts/generic/simple-chat.md"))

    assert transcript.client == "generic"
    assert transcript.messages[0].role == "user"
    assert "pytest" in transcript.messages[0].content


def test_validate_candidate_requires_valid_uri_and_evidence():
    candidate = MemoryCandidate(
        uri="project://local/demo/commands",
        type="project_command",
        scope="project",
        content="Use pytest for tests.",
        summary="Use pytest.",
        confidence=0.9,
        risk="low",
        evidence="user stated test command",
    )

    validate_candidate(candidate)


def test_route_candidates_auto_writes_low_risk_and_queues_high_impact(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()
    queue = ReviewQueue(tmp_path / "review-queue.jsonl")
    low_risk = MemoryCandidate(
        uri="project://local/demo/commands",
        type="project_command",
        scope="project",
        content="Use pytest for tests.",
        summary="Use pytest.",
        confidence=0.9,
        risk="low",
        evidence="user stated test command",
    )
    high_impact = MemoryCandidate(
        uri="project://local/demo/testing",
        type="testing_rule",
        scope="project",
        content="All tests must use pytest.",
        summary="Testing rule uses pytest.",
        confidence=0.9,
        risk="low",
        evidence="user stated testing rule",
    )

    result = route_candidates([low_risk, high_impact], store, queue, auto_write_confidence=0.85)

    assert result == {"auto_approved": 1, "queued": 1, "discarded": 0}
    assert len(store.search("pytest", limit=10)) == 1
    assert len(queue.list_pending()) == 1
```

- [ ] **Step 3: Run test to verify it fails**

Run:

```bash
pytest tests/unit/test_extraction.py -v
```

Expected: FAIL because extraction and adapter modules do not exist.

- [ ] **Step 4: Implement generic adapter and transcript normalization**

Create `src/ai_memory/adapters/__init__.py`:

```python
__all__ = []
```

Create `src/ai_memory/adapters/base.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ai_memory.core.models import NormalizedTranscript


class ClientAdapter(Protocol):
    name: str

    def discover(self) -> list[Path]:
        raise NotImplementedError

    def normalize(self, source: Path) -> NormalizedTranscript:
        raise NotImplementedError
```

Create `src/ai_memory/adapters/generic_transcript.py`:

```python
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
            stripped = line.strip()
            if stripped.startswith("User:"):
                messages.append(NormalizedMessage(role="user", content=stripped.removeprefix("User:").strip()))
            elif stripped.startswith("Assistant:"):
                messages.append(NormalizedMessage(role="assistant", content=stripped.removeprefix("Assistant:").strip()))
        if not messages:
            messages.append(NormalizedMessage(role="transcript", content=text))
        session_id = "sess_" + hashlib.sha1(str(source.resolve()).encode()).hexdigest()[:16]
        return NormalizedTranscript(
            session_id=session_id,
            client=self.name,
            source_path=str(source),
            messages=tuple(messages),
        )
```

- [ ] **Step 5: Implement candidate validation and routing**

Create `src/ai_memory/extraction/__init__.py`:

```python
__all__ = []
```

Create `src/ai_memory/extraction/validator.py`:

```python
from __future__ import annotations

from ai_memory.core.models import MemoryCandidate
from ai_memory.core.uri import validate_memory_uri
from ai_memory.privacy.redactor import redact_secrets


def validate_candidate(candidate: MemoryCandidate) -> None:
    validate_memory_uri(candidate.uri)
    if not candidate.content.strip():
        raise ValueError("candidate content is required")
    if not candidate.evidence.strip():
        raise ValueError("candidate evidence is required")
    if not 0 <= candidate.confidence <= 1:
        raise ValueError("candidate confidence must be between 0 and 1")
    if redact_secrets(candidate.content) != candidate.content:
        raise ValueError("candidate content contains sensitive material")
```

Create `src/ai_memory/extraction/router.py`:

```python
from __future__ import annotations

from ai_memory.core.models import MemoryCandidate
from ai_memory.core.policy import route_candidate
from ai_memory.extraction.validator import validate_candidate
from ai_memory.review.queue import ReviewQueue
from ai_memory.store.sqlite import SQLiteMemoryStore


def route_candidates(
    candidates: list[MemoryCandidate],
    store: SQLiteMemoryStore,
    queue: ReviewQueue,
    auto_write_confidence: float,
) -> dict[str, int]:
    result = {"auto_approved": 0, "queued": 0, "discarded": 0}
    for candidate in candidates:
        try:
            validate_candidate(candidate)
        except ValueError:
            result["discarded"] += 1
            continue
        decision = route_candidate(candidate, auto_write_confidence)
        if decision.action == "auto_write":
            store.create_memory(candidate, status="auto_approved", change_reason=decision.reason)
            result["auto_approved"] += 1
        elif decision.action == "review":
            queue.enqueue(candidate, decision.reason)
            result["queued"] += 1
        else:
            result["discarded"] += 1
    return result
```

- [ ] **Step 6: Implement extractor provider interfaces**

Create `src/ai_memory/extraction/providers/__init__.py`:

```python
__all__ = []
```

Create `src/ai_memory/extraction/providers/base.py`:

```python
from __future__ import annotations

from typing import Protocol

from ai_memory.core.models import MemoryCandidate, NormalizedTranscript


class ExtractorProvider(Protocol):
    def extract(self, transcript: NormalizedTranscript) -> list[MemoryCandidate]:
        raise NotImplementedError
```

Create `src/ai_memory/extraction/providers/command.py`:

```python
from __future__ import annotations

import json
import subprocess
from dataclasses import asdict

from ai_memory.core.models import MemoryCandidate, NormalizedTranscript


class CommandExtractorProvider:
    def __init__(self, command: str):
        self.command = command

    def extract(self, transcript: NormalizedTranscript) -> list[MemoryCandidate]:
        payload = json.dumps(asdict(transcript), ensure_ascii=False)
        result = subprocess.run(
            self.command,
            input=payload,
            capture_output=True,
            text=True,
            shell=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "extractor command failed")
        data = json.loads(result.stdout)
        if not isinstance(data, list):
            raise ValueError("extractor command must return a JSON list")
        candidates = []
        for item in data:
            item["tags"] = tuple(item.get("tags", ()))
            item["triggers"] = tuple(item.get("triggers", ()))
            candidates.append(MemoryCandidate(**item))
        return candidates
```

Create `src/ai_memory/extraction/transcript.py`:

```python
from __future__ import annotations

from ai_memory.core.models import NormalizedTranscript


def transcript_text(transcript: NormalizedTranscript) -> str:
    return "\n".join(f"{message.role}: {message.content}" for message in transcript.messages)
```

- [ ] **Step 7: Run extraction tests**

Run:

```bash
pytest tests/unit/test_extraction.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/ai_memory/extraction src/ai_memory/adapters tests/fixtures/transcripts/generic/simple-chat.md tests/unit/test_extraction.py
git commit -m "feat: add transcript extraction pipeline"
```

---

### Task 7: Implement MCP tool functions and server entry point

**Files:**
- Create: `src/ai_memory/mcp/__init__.py`
- Create: `src/ai_memory/mcp/tools.py`
- Create: `src/ai_memory/mcp/server.py`
- Modify: `src/ai_memory/cli/main.py`
- Test: `tests/unit/test_mcp_tools.py`

- [ ] **Step 1: Write failing MCP tool tests**

Create `tests/unit/test_mcp_tools.py`:

```python
from pathlib import Path

from ai_memory.core.models import MemoryCandidate
from ai_memory.mcp.tools import memory_context, memory_read, memory_search, memory_write
from ai_memory.store.sqlite import SQLiteMemoryStore
from ai_memory.review.queue import ReviewQueue


def test_memory_write_and_search(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()
    queue = ReviewQueue(tmp_path / "review-queue.jsonl")

    write_result = memory_write(
        store=store,
        queue=queue,
        payload={
            "uri": "project://local/demo/commands",
            "type": "project_command",
            "scope": "project",
            "content": "Use pytest for tests.",
            "summary": "Use pytest.",
            "confidence": 0.9,
            "risk": "low",
            "evidence": "manual MCP write",
        },
    )

    assert write_result["status"] == "auto_approved"
    search_result = memory_search(store=store, query="pytest", limit=5)
    assert search_result["items"][0]["content"] == "Use pytest for tests."


def test_memory_context_and_read(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()
    record = store.create_memory(
        MemoryCandidate(
            uri="project://local/demo/commands",
            type="project_command",
            scope="project",
            content="Use pytest for tests.",
            summary="Use pytest.",
            confidence=0.9,
            risk="low",
            evidence="test",
            tags=("pytest",),
            triggers=("pytest",),
        ),
        status="auto_approved",
        change_reason="test",
    )

    context = memory_context(store=store, prompt="pytest", max_items=5)
    assert "Use pytest for tests." in context["context"]

    read_result = memory_read(store=store, memory_id=record.id)
    assert read_result["item"]["id"] == record.id
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/unit/test_mcp_tools.py -v
```

Expected: FAIL because MCP modules do not exist.

- [ ] **Step 3: Implement MCP tool functions**

Create `src/ai_memory/mcp/__init__.py`:

```python
__all__ = []
```

Create `src/ai_memory/mcp/tools.py`:

```python
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ai_memory.core.models import MemoryCandidate
from ai_memory.extraction.router import route_candidates
from ai_memory.retrieval.assembler import assemble_context
from ai_memory.retrieval.ranking import rank_records
from ai_memory.review.queue import ReviewQueue
from ai_memory.store.sqlite import SQLiteMemoryStore


def memory_search(store: SQLiteMemoryStore, query: str, limit: int = 10) -> dict[str, Any]:
    records = store.search(query, limit)
    return {"items": [asdict(record) for record in records]}


def memory_context(store: SQLiteMemoryStore, prompt: str, max_items: int = 12) -> dict[str, Any]:
    records = rank_records(store.search(prompt, max_items))
    return {"context": assemble_context(records[:max_items]), "items": [asdict(record) for record in records[:max_items]]}


def memory_read(store: SQLiteMemoryStore, memory_id: str) -> dict[str, Any]:
    record = store.get_memory(memory_id)
    if record is None:
        return {"item": None}
    return {"item": asdict(record)}


def memory_write(store: SQLiteMemoryStore, queue: ReviewQueue, payload: dict[str, Any]) -> dict[str, Any]:
    payload["tags"] = tuple(payload.get("tags", ()))
    payload["triggers"] = tuple(payload.get("triggers", ()))
    candidate = MemoryCandidate(**payload)
    result = route_candidates([candidate], store, queue, auto_write_confidence=0.85)
    if result["auto_approved"] == 1:
        return {"status": "auto_approved"}
    if result["queued"] == 1:
        return {"status": "queued"}
    return {"status": "discarded"}
```

- [ ] **Step 4: Implement MCP server entry point**

Create `src/ai_memory/mcp/server.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from ai_memory.review.queue import ReviewQueue
from ai_memory.store.sqlite import SQLiteMemoryStore
from ai_memory.mcp.tools import memory_context, memory_read, memory_search, memory_write


def build_server(home: Path | None = None) -> FastMCP:
    memory_home = home or Path.home() / ".ai-memory"
    store = SQLiteMemoryStore(memory_home / "memory.db")
    store.initialize()
    queue = ReviewQueue(memory_home / "review-queue.jsonl")
    server = FastMCP("ai-memory")

    @server.tool()
    def memory_search_tool(query: str, limit: int = 10) -> dict[str, Any]:
        return memory_search(store, query, limit)

    @server.tool()
    def memory_context_tool(prompt: str, max_items: int = 12) -> dict[str, Any]:
        return memory_context(store, prompt, max_items)

    @server.tool()
    def memory_read_tool(memory_id: str) -> dict[str, Any]:
        return memory_read(store, memory_id)

    @server.tool()
    def memory_write_tool(payload: dict[str, Any]) -> dict[str, Any]:
        return memory_write(store, queue, payload)

    return server


def main() -> None:
    build_server().run()
```

- [ ] **Step 5: Add CLI `mcp serve` placeholder-free command**

Modify `src/ai_memory/cli/main.py`:

- Add a subparser named `mcp` with nested `serve` command.
- In `run`, when command is `mcp` and subcommand is `serve`, call `ai_memory.mcp.server.main()`.

Use this code shape:

```python
mcp_parser = subparsers.add_parser("mcp", help="Run MCP server commands")
mcp_subparsers = mcp_parser.add_subparsers(dest="mcp_command", required=True)
mcp_subparsers.add_parser("serve", help="Serve ai-memory MCP tools")
```

and:

```python
if args.command == "mcp" and args.mcp_command == "serve":
    from ai_memory.mcp.server import main as mcp_main
    mcp_main()
    return 0
```

- [ ] **Step 6: Run MCP tests**

Run:

```bash
pytest tests/unit/test_mcp_tools.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/ai_memory/mcp src/ai_memory/cli/main.py tests/unit/test_mcp_tools.py
git commit -m "feat: add MCP memory tools"
```

---

### Task 8: Add Claude/Codex/Gemini adapters and `aiwrap` skeleton

**Files:**
- Create: `src/ai_memory/adapters/claude_code.py`
- Create: `src/ai_memory/adapters/codex_cli.py`
- Create: `src/ai_memory/adapters/gemini_cli.py`
- Create: `src/ai_memory/wrappers/__init__.py`
- Create: `src/ai_memory/wrappers/aiwrap.py`
- Modify: `src/ai_memory/cli/main.py`
- Test: `tests/unit/test_adapters.py`

- [ ] **Step 1: Write failing adapter and wrapper tests**

Create `tests/unit/test_adapters.py`:

```python
from pathlib import Path

from ai_memory.adapters.claude_code import ClaudeCodeAdapter
from ai_memory.adapters.codex_cli import CodexCliAdapter
from ai_memory.adapters.gemini_cli import GeminiCliAdapter
from ai_memory.wrappers.aiwrap import build_wrapped_prompt


def test_claude_adapter_discovers_project_jsonl(tmp_path: Path):
    projects = tmp_path / ".claude" / "projects" / "demo"
    projects.mkdir(parents=True)
    session = projects / "session.jsonl"
    session.write_text('{"type":"user","message":"hello"}\n', encoding="utf-8")

    adapter = ClaudeCodeAdapter(home=tmp_path)
    sources = adapter.discover()

    assert sources == [session]


def test_codex_and_gemini_adapters_return_empty_when_missing(tmp_path: Path):
    assert CodexCliAdapter(home=tmp_path).discover() == []
    assert GeminiCliAdapter(home=tmp_path).discover() == []


def test_build_wrapped_prompt_prepends_context():
    prompt = build_wrapped_prompt("# Retrieved Memory\n- Use pytest", "fix tests")

    assert prompt.startswith("# Retrieved Memory")
    assert prompt.endswith("fix tests")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/unit/test_adapters.py -v
```

Expected: FAIL because adapters and wrapper do not exist.

- [ ] **Step 3: Implement client adapters**

Create `src/ai_memory/adapters/claude_code.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from ai_memory.core.models import NormalizedMessage, NormalizedTranscript


class ClaudeCodeAdapter:
    name = "claude-code"

    def __init__(self, home: Path | None = None):
        self.home = home or Path.home()

    def discover(self) -> list[Path]:
        projects = self.home / ".claude" / "projects"
        if not projects.exists():
            return []
        return sorted(projects.rglob("*.jsonl"))

    def normalize(self, source: Path) -> NormalizedTranscript:
        messages = []
        for line in source.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            role = str(data.get("type", data.get("role", "event")))
            content = data.get("message", data.get("content", ""))
            if isinstance(content, dict):
                content = json.dumps(content, ensure_ascii=False)
            messages.append(NormalizedMessage(role=role, content=str(content)))
        return NormalizedTranscript(
            session_id=f"sess_{source.stem}",
            client=self.name,
            source_path=str(source),
            messages=tuple(messages),
        )
```

Create `src/ai_memory/adapters/codex_cli.py`:

```python
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
```

Create `src/ai_memory/adapters/gemini_cli.py`:

```python
from __future__ import annotations

from pathlib import Path

from ai_memory.adapters.generic_transcript import GenericTranscriptAdapter


class GeminiCliAdapter(GenericTranscriptAdapter):
    name = "gemini-cli"

    def __init__(self, home: Path | None = None):
        self.home = home or Path.home()

    def discover(self) -> list[Path]:
        gemini_home = self.home / ".gemini"
        if not gemini_home.exists():
            return []
        return sorted(path for path in gemini_home.rglob("*") if path.is_file() and path.suffix in {".md", ".json", ".jsonl", ".txt"})
```

- [ ] **Step 4: Implement `aiwrap` prompt builder**

Create `src/ai_memory/wrappers/__init__.py`:

```python
__all__ = []
```

Create `src/ai_memory/wrappers/aiwrap.py`:

```python
from __future__ import annotations

import argparse
import subprocess
from typing import Sequence


def build_wrapped_prompt(context: str, prompt: str) -> str:
    return f"{context.rstrip()}\n\n# User Request\n{prompt}"


def run(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aiwrap")
    parser.add_argument("client")
    parser.add_argument("prompt", nargs="?")
    args, remainder = parser.parse_known_args(argv)

    if args.prompt is None:
        parser.error("aiwrap requires a prompt for the first version")
    command = [args.client, build_wrapped_prompt("", args.prompt), *remainder]
    completed = subprocess.run(command, check=False)
    return completed.returncode


def main() -> None:
    raise SystemExit(run())
```

- [ ] **Step 5: Add CLI `discover` command**

Modify `src/ai_memory/cli/main.py`:

- Add a `discover` subparser with `--client` and `--home`.
- Map `claude-code`, `codex-cli`, and `gemini-cli` to their adapters.
- Print one path per discovered source.

Use this helper in the file:

```python
def adapter_for(client: str, home: Path):
    if client == "claude-code":
        from ai_memory.adapters.claude_code import ClaudeCodeAdapter
        return ClaudeCodeAdapter(home=home)
    if client == "codex-cli":
        from ai_memory.adapters.codex_cli import CodexCliAdapter
        return CodexCliAdapter(home=home)
    if client == "gemini-cli":
        from ai_memory.adapters.gemini_cli import GeminiCliAdapter
        return GeminiCliAdapter(home=home)
    raise ValueError(f"Unsupported client: {client}")
```

- [ ] **Step 6: Run adapter tests**

Run:

```bash
pytest tests/unit/test_adapters.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/ai_memory/adapters src/ai_memory/wrappers src/ai_memory/cli/main.py tests/unit/test_adapters.py
git commit -m "feat: add initial client adapters"
```

---

### Task 9: Add CLI review approval, rejection, import, capture, and doctor commands

**Files:**
- Modify: `src/ai_memory/cli/main.py`
- Test: extend `tests/unit/test_extraction.py`
- Test: extend `tests/unit/test_privacy_review.py`

- [ ] **Step 1: Add failing CLI import and review tests**

Append to `tests/unit/test_privacy_review.py`:

```python
from ai_memory.cli.main import run


def test_cli_review_lists_empty_queue(tmp_path: Path, capsys):
    home = tmp_path / ".ai-memory"
    run(["init", "--home", str(home)])

    assert run(["review", "--home", str(home)]) == 0
    output = capsys.readouterr().out
    assert "No pending review items" in output
```

Append to `tests/unit/test_extraction.py`:

```python
from ai_memory.cli.main import run


def test_cli_import_generic_archive_only(tmp_path: Path, capsys):
    home = tmp_path / ".ai-memory"
    transcript = Path("tests/fixtures/transcripts/generic/simple-chat.md")
    run(["init", "--home", str(home)])

    assert run(["import", "--client", "generic", "--path", str(transcript), "--home", str(home), "--archive-only"]) == 0
    output = capsys.readouterr().out

    assert "Transcript archived" in output
    assert any((home / "raw" / "generic").iterdir())
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/test_privacy_review.py tests/unit/test_extraction.py -v
```

Expected: FAIL because `review` and `import` CLI commands are not implemented.

- [ ] **Step 3: Add `review` CLI command**

Modify `src/ai_memory/cli/main.py`:

- Add `review` parser with `--home`.
- Add `approve` parser with `review_id` and `--home`.
- Add `reject` parser with `review_id` and `--home`.
- Use `ReviewQueue` to list and mark items.

Implementation logic:

```python
if args.command == "review":
    queue = ReviewQueue(args.home / "review-queue.jsonl")
    items = queue.list_pending()
    if not items:
        print("No pending review items")
        return 0
    for item in items:
        print(f"{item.id} {item.candidate.uri} {item.reason}")
    return 0

if args.command == "approve":
    ReviewQueue(args.home / "review-queue.jsonl").mark(args.review_id, "approved")
    print(f"Approved {args.review_id}")
    return 0

if args.command == "reject":
    ReviewQueue(args.home / "review-queue.jsonl").mark(args.review_id, "rejected")
    print(f"Rejected {args.review_id}")
    return 0
```

Add imports:

```python
from ai_memory.review.queue import ReviewQueue
```

- [ ] **Step 4: Add `import` CLI archive-only command**

Modify `src/ai_memory/cli/main.py`:

- Add `import` parser with `--client`, `--path`, `--home`, and `--archive-only`.
- For first version, support only `--client generic` with a path.
- Copy the transcript into `home/raw/generic/<filename>`.

Implementation logic:

```python
if args.command == "import":
    if args.client != "generic":
        print("Only generic import is supported by this command in the first version")
        return 2
    source = args.path
    raw_dir = args.home / "raw" / "generic"
    raw_dir.mkdir(parents=True, exist_ok=True)
    target = raw_dir / source.name
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Transcript archived at {target}")
    return 0
```

- [ ] **Step 5: Run CLI tests**

Run:

```bash
pytest tests/unit/test_privacy_review.py tests/unit/test_extraction.py -v
```

Expected: PASS.

- [ ] **Step 6: Run all unit tests**

Run:

```bash
pytest tests/unit -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/ai_memory/cli/main.py tests/unit/test_privacy_review.py tests/unit/test_extraction.py
git commit -m "feat: add review and import CLI commands"
```

---

### Task 10: Add documentation, smoke checks, and final verification

**Files:**
- Create: `README.md`
- Create: `docs/architecture.md`
- Create: `docs/privacy.md`
- Modify: `docs/superpowers/plans/2026-04-29-ai-memory-implementation.md` only if execution notes reveal inaccuracies.

- [ ] **Step 1: Write README with exact first-version commands**

Create `README.md`:

```markdown
# ai-memory

Local-first multi-tool memory for AI coding agents.

## First-version scope

- SQLite memory store.
- CLI commands for init, add, search, context, import, review, and MCP serving.
- JSONL review queue.
- Privacy redaction for common secrets.
- Generic transcript import.
- Initial Claude Code, Codex CLI, and Gemini CLI adapters.

## Install for development

```bash
python -m pip install -e ".[dev]"
```

## Initialize

```bash
ai-memory init
```

## Add and retrieve memory

```bash
ai-memory add project://local/demo/commands "Use pytest for tests."
ai-memory search pytest
ai-memory context --prompt "run tests"
```

## Import a generic transcript

```bash
ai-memory import --client generic --path ./chat.md --archive-only
```

## Review queue

```bash
ai-memory review
ai-memory approve rev_example
ai-memory reject rev_example
```

## MCP server

```bash
ai-memory mcp serve
```
```

- [ ] **Step 2: Write architecture docs**

Create `docs/architecture.md`:

```markdown
# Architecture

`ai-memory` is organized around a tool-agnostic core. Tool-specific behavior lives in adapters.

## Layers

- `core`: models, URI parsing, config, and write policy.
- `store`: SQLite persistence and FTS.
- `retrieval`: environment detection, ranking, and context assembly.
- `extraction`: transcript normalization, candidate validation, provider interface, and routing.
- `privacy`: redaction and sensitive path detection.
- `review`: JSONL review queue.
- `cli`: user commands.
- `mcp`: MCP tools and server.
- `adapters`: Claude Code, Codex CLI, Gemini CLI, and generic transcript discovery.

## Data flow

Session start calls `ai-memory context`, which searches approved memory and emits markdown or hook JSON.

Session end calls `ai-memory capture` or `ai-memory import`, which archives transcript content and routes extracted candidates through the write policy.
```

- [ ] **Step 3: Write privacy docs**

Create `docs/privacy.md`:

```markdown
# Privacy

`ai-memory` must not store secrets as durable memory.

## Redacted content

- Bearer tokens.
- API key assignments.
- Password assignments.
- Private key blocks.
- Database URL passwords.

## Sensitive paths

The first version treats these as sensitive:

- `.env` and `.env.*`
- `*.pem`
- `*.key`
- `id_rsa`
- `id_ed25519`
- `credentials.json`
- paths under `.ssh` or `.aws`

## Review policy

High-impact memory types such as user preferences, security constraints, testing rules, API contracts, and architecture decisions enter the review queue instead of being auto-written.
```

- [ ] **Step 4: Run full test suite**

Run:

```bash
pytest -v
```

Expected: PASS.

- [ ] **Step 5: Run CLI smoke test in a temporary home**

Run:

```bash
TMP_HOME="$(mktemp -d)" && ai-memory init --home "$TMP_HOME" && ai-memory add project://local/demo/commands "Use pytest for tests." --home "$TMP_HOME" && ai-memory search pytest --home "$TMP_HOME" && ai-memory context --home "$TMP_HOME" --prompt "run tests"
```

Expected output contains:

```text
Initialized ai-memory
Added memory
Use pytest for tests.
# Retrieved Memory
```

- [ ] **Step 6: Verify hook JSON output**

Run:

```bash
TMP_HOME="$(mktemp -d)" && ai-memory init --home "$TMP_HOME" && ai-memory context --home "$TMP_HOME" --format hook-json --event SessionStart
```

Expected output is JSON containing:

```json
{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"# Retrieved Memory\n\nNo relevant approved memory found."}}
```

- [ ] **Step 7: Commit docs and final verification updates**

```bash
git add README.md docs/architecture.md docs/privacy.md
git commit -m "docs: add ai-memory usage and architecture notes"
```

---

## Self-Review Checklist

Spec coverage:

- Hybrid Python architecture: covered by Tasks 1 through 10.
- SQLite store, versions, sources, FTS: covered by Task 3.
- URI model and policy: covered by Task 2.
- Review queue: covered by Task 4 and Task 9.
- Privacy redaction and sensitive paths: covered by Task 4 and Task 10.
- Context retrieval and hook JSON: covered by Task 5.
- Transcript import/capture foundation: covered by Task 6 and Task 9.
- MCP surface: covered by Task 7.
- Claude/Codex/Gemini/generic adapters: covered by Task 8.
- Tests and docs: covered throughout and finalized in Task 10.

Known deferrals from the approved spec:

- Web dashboard is out of scope.
- Remote HTTP service is out of scope.
- Team permissions are out of scope.
- Required vector database is out of scope.
- Deep adapter support for every AI tool is out of scope.
- Automatic Claude Code settings modification is out of scope for this first implementation plan; hook JSON output is implemented for manual configuration.

Type consistency:

- Memory candidate type is `MemoryCandidate` in all tasks.
- Store class is `SQLiteMemoryStore` in all tasks.
- Review queue class is `ReviewQueue` in all tasks.
- MCP function names are `memory_context`, `memory_search`, `memory_read`, and `memory_write` in all tasks.
- CLI command is `ai-memory`; wrapper command is `aiwrap`.
