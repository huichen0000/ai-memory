from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ai_memory.core.config import load_config
from ai_memory.store.sqlite import SQLiteMemoryStore


@dataclass(frozen=True)
class UpdateSummary:
    memory_id: str
    uri: str
    old_content: str
    new_content: str
    version_created: bool


def update_memory(
    *,
    memory_id: str,
    new_content: str,
    home: Path,
) -> tuple[int, str]:
    config = load_config(home)
    store = SQLiteMemoryStore(config.store_path)
    store.initialize()

    record = store.get_memory(memory_id)
    if record is None:
        return 2, f"Memory not found: {memory_id}"

    if record.status not in {"approved", "auto_approved"}:
        return 2, f"Cannot update non-approved memory: {memory_id}"

    if record.content == new_content:
        return 0, f"No change needed for {memory_id}"

    updated = store.update_memory(memory_id, new_content, "manual update via CLI")
    return 0, f"Updated {memory_id} (URI: {updated.uri})"


def show_memory(
    *,
    memory_id: str,
    home: Path,
) -> tuple[int, str]:
    config = load_config(home)
    store = SQLiteMemoryStore(config.store_path)
    store.initialize()

    record = store.get_memory(memory_id)
    if record is None:
        return 2, f"Memory not found: {memory_id}"

    lines = [
        f"ID: {record.id}",
        f"URI: {record.uri}",
        f"Type: {record.type}",
        f"Scope: {record.scope}",
        f"Status: {record.status}",
        f"Confidence: {record.confidence}",
        f"Risk: {record.risk}",
        "",
        "Content:",
        record.content,
    ]
    if record.summary:
        lines.append("")
        lines.append(f"Summary: {record.summary}")
    if record.triggers:
        lines.append("")
        lines.append(f"Triggers: {', '.join(record.triggers)}")
    lines.append("")
    lines.append(f"Created: {record.created_at}")
    lines.append(f"Updated: {record.updated_at}")

    versions = store.list_versions(memory_id)
    if versions:
        lines.append("")
        lines.append(f"Versions: {len(versions)}")
        for i, v in enumerate(versions):
            lines.append(f"  [{i}] {v.get('content', '')[:60]}... - {v.get('updated_at', '')}")

    return 0, "\n".join(lines)


def list_memories(
    *,
    home: Path,
    status_filter: tuple[str, ...] | None = None,
    uri_pattern: str | None = None,
    limit: int = 50,
) -> tuple[int, str]:
    config = load_config(home)
    store = SQLiteMemoryStore(config.store_path)
    store.initialize()

    records = store.list_all(status_filter=status_filter)
    if uri_pattern:
        records = [r for r in records if uri_pattern in r.uri]
    records = records[:limit]

    if not records:
        return 0, "No memories found"

    lines = []
    for record in records:
        lines.append(f"{record.id} [{record.status}] {record.uri}")
        lines.append(f"  type={record.type} scope={record.scope} confidence={record.confidence}")
        lines.append(f"  {record.content[:80]}...")
        lines.append("")

    return 0, "\n".join(lines)