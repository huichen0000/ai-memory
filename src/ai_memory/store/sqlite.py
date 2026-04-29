from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

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

    def _replace_fts(
        self,
        db: sqlite3.Connection,
        record: MemoryRecord,
        tags: list[str] | tuple[str, ...],
        triggers: list[str] | tuple[str, ...],
    ) -> None:
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
