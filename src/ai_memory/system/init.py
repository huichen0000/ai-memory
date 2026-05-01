from __future__ import annotations

from ai_memory.core.models import MemoryCandidate
from ai_memory.store.sqlite import SQLiteMemoryStore


SYSTEM_MEMORIES = (
    MemoryCandidate(
        uri="system://boot",
        type="tool_note",
        scope="system",
        content="Review system://boot, system://recent, and system://glossary for session-start context before working in a new project.",
        summary="Session-start system memory review",
        confidence=1.0,
        risk="low",
        evidence="system bootstrapping curated memory",
        tags=("system", "boot", "session-start"),
        triggers=("session-start", "new-project", "context"),
    ),
    MemoryCandidate(
        uri="system://recent",
        type="tool_note",
        scope="system",
        content="Check recent memories for context continuity. Use 'ai-memory context --prompt recent' to retrieve recently added memories relevant to current work.",
        summary="Recent memory continuity check",
        confidence=1.0,
        risk="low",
        evidence="system bootstrapping curated memory",
        tags=("system", "recent", "continuity"),
        triggers=("recent", "continuity", "context"),
    ),
    MemoryCandidate(
        uri="system://glossary",
        type="tool_note",
        scope="system",
        content="Use project:// URIs for project-specific context, branch:// for branch-specific state, and path:// for directory-specific rules. Avoid global:// unless explicitly needed.",
        summary="URI namespace usage guide",
        confidence=1.0,
        risk="low",
        evidence="system bootstrapping curated memory",
        tags=("system", "glossary", "uri", "namespace"),
        triggers=("uri", "namespace", "scope", "glossary"),
    ),
    MemoryCandidate(
        uri="system://index/project",
        type="tool_note",
        scope="system",
        content="Project-scoped memories apply to all branches and paths within a repo. Use project://<repo>/<type> for commands, testing rules, coding style, and architecture decisions.",
        summary="Project scope index",
        confidence=1.0,
        risk="low",
        evidence="system bootstrapping curated memory",
        tags=("system", "index", "project"),
        triggers=("project", "repo", "scope"),
    ),
    MemoryCandidate(
        uri="system://index/branch",
        type="tool_note",
        scope="system",
        content="Branch-scoped memories apply only within a specific git branch. Use branch://<repo>/<branch>/<type> for branch-specific state, temporary workarounds, and feature flags.",
        summary="Branch scope index",
        confidence=1.0,
        risk="low",
        evidence="system bootstrapping curated memory",
        tags=("system", "index", "branch"),
        triggers=("branch", "git", "feature"),
    ),
    MemoryCandidate(
        uri="system://index/path",
        type="tool_note",
        scope="system",
        content="Path-scoped memories apply within a specific directory tree. Use path://<repo>/<path> for directory-specific rules, test commands, and local conventions.",
        summary="Path scope index",
        confidence=1.0,
        risk="low",
        evidence="system bootstrapping curated memory",
        tags=("system", "index", "path"),
        triggers=("path", "directory", "local"),
    ),
    MemoryCandidate(
        uri="system://boot/write-policy",
        type="tool_note",
        scope="system",
        content="Low-risk high-confidence memories (project_command, branch_state, task_todo, pitfall) may be auto-approved. High-impact types (user_preference, architecture_decision, security_constraint) always require review.",
        summary="Write policy reminder",
        confidence=1.0,
        risk="low",
        evidence="system bootstrapping curated memory",
        tags=("system", "boot", "policy", "write"),
        triggers=("write", "policy", "review", "auto-approved"),
    ),
    MemoryCandidate(
        uri="system://boot/privacy",
        type="tool_note",
        scope="system",
        content="Secrets are redacted during transcript normalization. Sensitive source paths (.env, credentials, .ssh, .aws, etc.) are rejected by default for raw archive. Use --allow-sensitive-source only for confirmed-safe transcripts.",
        summary="Privacy policy reminder",
        confidence=1.0,
        risk="low",
        evidence="system bootstrapping curated memory",
        tags=("system", "boot", "privacy", "redaction"),
        triggers=("privacy", "secret", "redaction", "sensitive"),
    ),
)


def seed_system_memories(store: SQLiteMemoryStore) -> tuple[int, int]:
    seeded = 0
    skipped = 0
    for candidate in SYSTEM_MEMORIES:
        existing = store.get_by_uri(candidate.uri)
        if existing is None:
            store.create_memory(candidate, status="approved", change_reason="system bootstrapping seed")
            seeded += 1
        else:
            skipped += 1
    return seeded, skipped