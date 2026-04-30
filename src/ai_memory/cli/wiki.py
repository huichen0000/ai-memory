from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ai_memory.core.config import load_config
from ai_memory.store.sqlite import SQLiteMemoryStore


@dataclass(frozen=True)
class WikiSection:
    scope: str
    memory_type: str | None = None


WIKI_SECTIONS = [
    WikiSection(scope="global"),
    WikiSection(scope="system"),
    WikiSection(scope="org"),
    WikiSection(scope="tool"),
    WikiSection(scope="project"),
    WikiSection(scope="branch"),
    WikiSection(scope="path"),
]


def run_wiki(
    *,
    home: Path,
    output_dir: Path | None,
    include_auto_approved: bool = False,
    types: tuple[str, ...] | None = None,
) -> int:
    config = load_config(home)
    store = SQLiteMemoryStore(config.store_path)
    store.initialize()

    out_dir = (output_dir or config.home / "wiki").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    statuses = ("approved",)
    if include_auto_approved:
        statuses = ("approved", "auto_approved")

    records = store.list_all()
    filtered = [r for r in records if r.status in statuses]

    if types:
        filtered = [r for r in filtered if r.type in types]

    _render_index(out_dir, filtered)
    _render_scoped_pages(out_dir, filtered)
    _render_log(out_dir, out_dir / "log.md", filtered)

    print(f"Wiki projection written to: {out_dir}")
    return 0


def _render_index(out_dir: Path, records: list) -> None:
    index = out_dir / "index.md"
    lines = [
        "# ai-memory Wiki",
        "",
        "This wiki is a read-only projection of approved SQLite memories.",
        "SQLite remains the canonical source of truth.",
        "",
        "## Scopes",
        "",
    ]

    scope_groups: dict[str, list] = {}
    for record in records:
        parsed = _parse_uri(record.uri)
        scope = parsed.get("namespace", "unknown")
        scope_groups.setdefault(scope, []).append(record)

    for section in WIKI_SECTIONS:
        scope = section.scope
        scope_records = scope_groups.get(scope, [])
        if not scope_records:
            continue
        lines.append(f"### {scope.upper()}")
        lines.append("")
        for record in scope_records:
            lines.append(f"- [{record.type}] {record.uri}")
        lines.append("")

    lines.append("## Type Index")
    lines.append("")
    type_groups: dict[str, list] = {}
    for record in records:
        type_groups.setdefault(record.type, []).append(record)

    for mtype, recs in sorted(type_groups.items()):
        lines.append(f"### {mtype}")
        lines.append("")
        for record in recs:
            lines.append(f"- {record.uri}")
        lines.append("")

    index.write_text("\n".join(lines), encoding="utf-8")


def _render_scoped_pages(out_dir: Path, records: list) -> None:
    namespace_dirs: dict[str, Path] = {}

    for record in records:
        parsed = _parse_uri(record.uri)
        namespace = parsed.get("namespace", "unknown")
        authority = parsed.get("authority", "")

        if namespace not in namespace_dirs:
            namespace_dirs[namespace] = out_dir / namespace
            namespace_dirs[namespace].mkdir(exist_ok=True)

        page_dir = namespace_dirs[namespace]
        if authority:
            safe_authority = _safe_filename(authority)
            page_dir = page_dir / safe_authority
            page_dir.mkdir(exist_ok=True)

        page = page_dir / "index.md"
        _render_memory_page(page, [r for r in records if _uri_namespace(r.uri) == namespace and _uri_authority(r.uri) == authority])


def _render_memory_page(page: Path, records: list) -> None:
    if not records:
        return
    lines = [f"# {records[0].uri}", ""]
    for record in records:
        lines.append(f"## [{record.type}] {record.id}")
        lines.append("")
        lines.append(record.content)
        lines.append("")
        if record.summary:
            lines.append(f"**Summary:** {record.summary}")
            lines.append("")
        lines.append(f"- Status: {record.status}")
        lines.append(f"- Confidence: {record.confidence}")
        if record.triggers:
            lines.append(f"- Triggers: {', '.join(record.triggers)}")
        lines.append("")

    page.write_text("\n".join(lines), encoding="utf-8")


def _render_log(out_dir: Path, log_path: Path, records: list) -> None:
    lines = ["# Operation Log", "", "This log records the current wiki projection.", ""]
    for record in records:
        lines.append(f"- [{record.status}] {record.uri} ({record.type}) - created {record.created_at}")
    log_path.write_text("\n".join(lines), encoding="utf-8")


def _parse_uri(uri: str) -> dict[str, str]:
    if "://" not in uri:
        return {}
    namespace, _, authority = uri.partition("://")
    return {"namespace": namespace, "authority": authority}


def _uri_namespace(uri: str) -> str:
    return _parse_uri(uri).get("namespace", "unknown")


def _uri_authority(uri: str) -> str:
    return _parse_uri(uri).get("authority", "")


def _safe_filename(name: str) -> str:
    name = re.sub(r"[^\w\-./]", "_", name)
    name = re.sub(r"_+", "_", name)
    return name.strip("_") or "unnamed"