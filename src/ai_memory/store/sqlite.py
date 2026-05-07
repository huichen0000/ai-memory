from __future__ import annotations

import fnmatch
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
                    updated_at TEXT NOT NULL,
                    owner_user_id TEXT
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
            columns = {row["name"] for row in db.execute("PRAGMA table_info(memories)").fetchall()}
            if "owner_user_id" not in columns:
                db.execute("ALTER TABLE memories ADD COLUMN owner_user_id TEXT")

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
            owner_user_id=candidate.owner_user_id,
        )
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO memories (
                    id, uri, type, scope, content, summary, status, confidence, risk,
                    repo_id, branch, path_glob, expires_at, created_at, updated_at, owner_user_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    record.owner_user_id,
                ),
            )
            db.execute(
                """
                INSERT INTO memory_sources (
                    id, memory_id, client, session_id, transcript_ref, evidence, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
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
                """
                INSERT INTO memory_versions (
                    id, memory_id, version, content, summary, status, changed_by, change_reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (new_id("ver"), memory_id, 1, record.content, record.summary, record.status, "ai-memory", change_reason, now),
            )
            self._replace_tags(db, memory_id, candidate.tags)
            self._replace_triggers(db, memory_id, candidate.triggers)
            self._replace_fts(db, record, candidate.tags, candidate.triggers)
        return record

    def append_source(self, memory_id: str, candidate: MemoryCandidate) -> None:
        now = utc_now_iso()
        with self.connect() as db:
            row = db.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
            if row is None:
                raise ValueError(f"Unknown memory id: {memory_id}")
            existing = self._record_from_row(row)
            if not _source_candidate_matches(existing, candidate):
                raise ValueError("source candidate does not match target memory")
            db.execute(
                """
                INSERT INTO memory_sources (
                    id, memory_id, client, session_id, transcript_ref, evidence, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
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

    def get_memory(self, memory_id: str) -> MemoryRecord | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
        return self._record_from_row(row) if row else None

    def get_by_uri(self, uri: str) -> MemoryRecord | None:
        with self.connect() as db:
            row = db.execute(
                """
                SELECT * FROM memories
                WHERE uri = ?
                  AND status IN ('approved', 'auto_approved')
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (uri,),
            ).fetchone()
        return self._record_from_row(row) if row else None

    def list_all(self, status_filter: tuple[str, ...] | None = None) -> list[MemoryRecord]:
        with self.connect() as db:
            if status_filter:
                placeholders = ",".join("?" * len(status_filter))
                rows = db.execute(
                    f"SELECT * FROM memories WHERE status IN ({placeholders}) ORDER BY updated_at DESC, id DESC",
                    status_filter,
                ).fetchall()
            else:
                rows = db.execute("SELECT * FROM memories ORDER BY updated_at DESC, id DESC").fetchall()
        return [self._record_from_row(row) for row in rows]

    def list_page(
        self,
        *,
        status_filter: tuple[str, ...] | None = None,
        type_filter: str | None = None,
        scope_filter: str | None = None,
        owner_user_id_filter: str | None = None,
        limit: int,
        offset: int = 0,
    ) -> list[MemoryRecord]:
        where_sql, params = _memory_filter_sql(status_filter, type_filter, scope_filter, owner_user_id_filter)
        with self.connect() as db:
            rows = db.execute(
                f"SELECT * FROM memories{where_sql} ORDER BY updated_at DESC, id DESC LIMIT ? OFFSET ?",
                (*params, limit, offset),
            ).fetchall()
        return [self._record_from_row(row) for row in rows]

    def count_all(
        self,
        *,
        status_filter: tuple[str, ...] | None = None,
        type_filter: str | None = None,
        scope_filter: str | None = None,
        owner_user_id_filter: str | None = None,
    ) -> int:
        where_sql, params = _memory_filter_sql(status_filter, type_filter, scope_filter, owner_user_id_filter)
        with self.connect() as db:
            return int(db.execute(f"SELECT COUNT(*) FROM memories{where_sql}", params).fetchone()[0])

    def get_stats(self) -> dict[str, Any]:
        with self.connect() as db:
            total = db.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            by_status = dict(db.execute("SELECT status, COUNT(*) FROM memories GROUP BY status").fetchall())
            by_type = dict(db.execute("SELECT type, COUNT(*) FROM memories GROUP BY type").fetchall())
            by_scope = dict(db.execute("SELECT scope, COUNT(*) FROM memories GROUP BY scope").fetchall())
        return {"total": total, "by_status": by_status, "by_type": by_type, "by_scope": by_scope}

    def list_contextual(self, environment: dict[str, str | None], limit: int) -> list[MemoryRecord]:
        del limit
        repo_id = environment.get("repo_id")
        branch = environment.get("branch")
        relative_path = environment.get("relative_path")
        with self.connect() as db:
            rows = db.execute(
                """
                SELECT DISTINCT memories.*
                FROM memories
                WHERE memories.status IN ('approved', 'auto_approved')
                  AND (
                    memories.scope IN ('global', 'system')
                    OR (? IS NOT NULL AND memories.repo_id = ?)
                    OR (
                        ? IS NOT NULL
                        AND ? IS NOT NULL
                        AND memories.repo_id = ?
                        AND memories.branch = ?
                    )
                  )
                """,
                (repo_id, repo_id, repo_id, branch, repo_id, branch),
            ).fetchall()
        records = [self._record_from_row(row) for row in rows]
        return [record for record in records if _matches_environment_path(record, relative_path)]

    def update_memory(self, memory_id: str, content: str, change_reason: str) -> MemoryRecord:
        now = utc_now_iso()
        with self.connect() as db:
            existing_row = db.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
            if existing_row is None:
                raise ValueError(f"Unknown memory id: {memory_id}")
            existing = self._record_from_row(existing_row)
            current_version = db.execute(
                "SELECT COALESCE(MAX(version), 0) FROM memory_versions WHERE memory_id = ?",
                (memory_id,),
            ).fetchone()[0]
            db.execute("UPDATE memories SET content = ?, updated_at = ? WHERE id = ?", (content, now, memory_id))
            db.execute(
                """
                INSERT INTO memory_versions (
                    id, memory_id, version, content, summary, status, changed_by, change_reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
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
            updated_row = db.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
            if updated_row is None:
                raise ValueError(f"Memory disappeared during update: {memory_id}")
            updated = self._record_from_row(updated_row)
            tags = [row["tag"] for row in db.execute("SELECT tag FROM memory_tags WHERE memory_id = ?", (memory_id,))]
            triggers = [row["trigger"] for row in db.execute("SELECT trigger FROM memory_triggers WHERE memory_id = ?", (memory_id,))]
            self._replace_fts(db, updated, tags, triggers)
            return updated

    def search(
        self,
        query: str,
        limit: int,
        offset: int = 0,
        *,
        status_filter: tuple[str, ...] | None = None,
        type_filter: str | None = None,
        scope_filter: str | None = None,
        owner_user_id_filter: str | None = None,
    ) -> list[MemoryRecord]:
        where_sql, params = _memory_filter_sql(
            status_filter or ("approved", "auto_approved"), type_filter, scope_filter, owner_user_id_filter
        )
        like_pattern = _like_pattern(query)
        with self.connect() as db:
            try:
                rows = db.execute(
                    f"""
                    SELECT *
                    FROM memories
                    {where_sql}
                      AND (
                        id IN (SELECT memory_id FROM memory_fts WHERE memory_fts MATCH ?)
                        OR uri LIKE ?
                        OR content LIKE ?
                        OR summary LIKE ?
                      )
                    ORDER BY updated_at DESC, id DESC
                    LIMIT ? OFFSET ?
                    """,
                    (*params, query, like_pattern, like_pattern, like_pattern, limit, offset),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = db.execute(
                    f"""
                    SELECT *
                    FROM memories
                    {where_sql}
                      AND (uri LIKE ? OR content LIKE ? OR summary LIKE ?)
                    ORDER BY updated_at DESC, id DESC
                    LIMIT ? OFFSET ?
                    """,
                    (*params, like_pattern, like_pattern, like_pattern, limit, offset),
                ).fetchall()
        return [self._record_from_row(row) for row in rows]

    def count_search(
        self,
        query: str,
        *,
        status_filter: tuple[str, ...] | None = None,
        type_filter: str | None = None,
        scope_filter: str | None = None,
        owner_user_id_filter: str | None = None,
    ) -> int:
        where_sql, params = _memory_filter_sql(
            status_filter or ("approved", "auto_approved"), type_filter, scope_filter, owner_user_id_filter
        )
        like_pattern = _like_pattern(query)
        with self.connect() as db:
            try:
                return int(
                    db.execute(
                        f"""
                        SELECT COUNT(*)
                        FROM memories
                        {where_sql}
                          AND (
                            id IN (SELECT memory_id FROM memory_fts WHERE memory_fts MATCH ?)
                            OR uri LIKE ?
                            OR content LIKE ?
                            OR summary LIKE ?
                          )
                        """,
                        (*params, query, like_pattern, like_pattern, like_pattern),
                    ).fetchone()[0]
                )
            except sqlite3.OperationalError:
                return int(
                    db.execute(
                        f"""
                        SELECT COUNT(*)
                        FROM memories
                        {where_sql}
                          AND (uri LIKE ? OR content LIKE ? OR summary LIKE ?)
                        """,
                        (*params, like_pattern, like_pattern, like_pattern),
                    ).fetchone()[0]
                )

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
        db.executemany("INSERT INTO memory_tags (memory_id, tag) VALUES (?, ?)", [(memory_id, tag) for tag in tags])

    def _replace_triggers(self, db: sqlite3.Connection, memory_id: str, triggers: tuple[str, ...]) -> None:
        db.execute("DELETE FROM memory_triggers WHERE memory_id = ?", (memory_id,))
        db.executemany("INSERT INTO memory_triggers (memory_id, trigger) VALUES (?, ?)", [(memory_id, trigger) for trigger in triggers])

    def _replace_fts(
        self,
        db: sqlite3.Connection,
        record: MemoryRecord,
        tags: list[str] | tuple[str, ...],
        triggers: list[str] | tuple[str, ...],
    ) -> None:
        db.execute("DELETE FROM memory_fts WHERE memory_id = ?", (record.id,))
        db.execute(
            """
            INSERT INTO memory_fts (memory_id, uri, content, summary, tags, triggers)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (record.id, record.uri, record.content, record.summary, " ".join(tags), " ".join(triggers)),
        )

    def _triggers_for(self, memory_id: str) -> tuple[str, ...]:
        with self.connect() as db:
            rows = db.execute("SELECT trigger FROM memory_triggers WHERE memory_id = ?", (memory_id,)).fetchall()
        return tuple(row["trigger"] for row in rows)

    def _record_from_row(self, row: sqlite3.Row) -> MemoryRecord:
        memory_id = row["id"]
        return MemoryRecord(
            id=memory_id,
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
            triggers=self._triggers_for(memory_id),
            owner_user_id=row["owner_user_id"],
        )


def _like_pattern(query: str) -> str:
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"



def _memory_filter_sql(
    status_filter: tuple[str, ...] | None,
    type_filter: str | None,
    scope_filter: str | None,
    owner_user_id_filter: str | None = None,
) -> tuple[str, tuple[str, ...]]:
    conditions: list[str] = []
    params: list[str] = []
    if status_filter:
        placeholders = ",".join("?" * len(status_filter))
        conditions.append(f"status IN ({placeholders})")
        params.extend(status_filter)
    if type_filter:
        conditions.append("type = ?")
        params.append(type_filter)
    if scope_filter:
        conditions.append("scope = ?")
        params.append(scope_filter)
    if owner_user_id_filter:
        conditions.append("owner_user_id = ?")
        params.append(owner_user_id_filter)
    if not conditions:
        return "", ()
    return " WHERE " + " AND ".join(conditions), tuple(params)


def _source_candidate_matches(record: MemoryRecord, candidate: MemoryCandidate) -> bool:
    return (
        record.uri == candidate.uri
        and record.type == candidate.type
        and record.content == candidate.content
        and record.summary == candidate.summary
        and record.scope == candidate.scope
        and record.repo_id == candidate.repo_id
        and record.branch == candidate.branch
        and record.path_glob == candidate.path_glob
    )


def _matches_environment_path(record: MemoryRecord, relative_path: str | None) -> bool:
    if record.scope != "path":
        return True
    if relative_path is None or record.path_glob is None:
        return False
    if fnmatch.fnmatch(relative_path, record.path_glob):
        return True
    if "/**/" in record.path_glob:
        return fnmatch.fnmatch(relative_path, record.path_glob.replace("/**/", "/"))
    return False
