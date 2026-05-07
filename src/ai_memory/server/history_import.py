from __future__ import annotations

import secrets
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ai_memory.core.config import AppConfig
from ai_memory.extraction.providers.command import CommandExtractorProvider
from ai_memory.history.initializer import HistoryInitOptions, run_history_init
from ai_memory.privacy.redactor import redact_secrets
from ai_memory.review.queue import ReviewQueue
from ai_memory.store.sqlite import SQLiteMemoryStore

ALLOWED_IMPORT_CLIENTS = {"claude-code", "codex-cli", "gemini-cli"}
MAX_IMPORT_SOURCE_BYTES = 10 * 1024 * 1024


def create_import_session(home: Path, owner_user_id: str, clients: list[str]) -> dict[str, Any]:
    _validate_clients(clients)
    session_id = "hist_sess_" + secrets.token_urlsafe(12).replace("-", "_")
    session_dir = _session_dir(home, session_id)
    session_dir.mkdir(parents=True, exist_ok=False)
    metadata = {"session_id": session_id, "owner_user_id": owner_user_id, "clients": clients}
    _metadata_path(home, session_id).write_text(_json_dumps(metadata), encoding="utf-8")
    return metadata


def store_import_source(home: Path, session_id: str, owner_user_id: str, payload: dict[str, Any], redact_archive: bool) -> dict[str, Any]:
    metadata = _load_session_metadata(home, session_id, owner_user_id)
    client = str(payload.get("client", ""))
    _validate_clients([client])
    if client not in metadata["clients"]:
        raise ValueError(f"Client is not enabled for this import session: {client}")
    content = payload.get("content")
    if not isinstance(content, str):
        raise ValueError("content is required")
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_IMPORT_SOURCE_BYTES:
        raise ValueError("source is too large")
    source_name = _safe_source_name(str(payload.get("name") or Path(str(payload.get("path") or "source.txt")).name))
    client_dir = _session_dir(home, session_id) / "sources" / client
    client_dir.mkdir(parents=True, exist_ok=True)
    target = _unique_target(client_dir, source_name)
    target.write_text(redact_secrets(content) if redact_archive else content, encoding="utf-8")
    return {"client": client, "name": target.name, "size": len(encoded)}


def process_import_session(
    *,
    home: Path,
    session_id: str,
    owner_user_id: str,
    config: AppConfig,
    store: SQLiteMemoryStore,
    queue: ReviewQueue,
    review_only: bool,
    auto_write_low_risk: bool,
) -> dict[str, Any]:
    _load_session_metadata(home, session_id, owner_user_id)
    source_root = _session_dir(home, session_id) / "sources"
    extractor = None
    if config.extractor_provider == "command" and config.extractor_command:
        extractor = CommandExtractorProvider(config.extractor_command)
    summary = run_history_init(
        options=HistoryInitOptions(
            clients=(),
            include_generic=tuple(source_root.iterdir()) if source_root.exists() else (),
            review_only=review_only,
            auto_write_low_risk=auto_write_low_risk,
            owner_user_id=owner_user_id,
        ),
        config=config,
        source_home=home,
        store=store,
        queue=queue,
        extractor=extractor,
    )
    return asdict(summary)


def _validate_clients(clients: list[str]) -> None:
    if not clients:
        raise ValueError("clients is required")
    unsupported = [client for client in clients if client not in ALLOWED_IMPORT_CLIENTS]
    if unsupported:
        raise ValueError(f"Unsupported history client: {unsupported[0]}")


def _sessions_dir(home: Path) -> Path:
    return home / "import-sessions"


def _session_dir(home: Path, session_id: str) -> Path:
    if not session_id.startswith("hist_sess_") or any(part in session_id for part in ("/", "\\", "..")):
        raise ValueError("Invalid import session id")
    return _sessions_dir(home) / session_id


def _metadata_path(home: Path, session_id: str) -> Path:
    return _session_dir(home, session_id) / "metadata.json"


def _load_session_metadata(home: Path, session_id: str, owner_user_id: str) -> dict[str, Any]:
    import json

    path = _metadata_path(home, session_id)
    if not path.is_file():
        raise ValueError("Unknown import session")
    metadata = json.loads(path.read_text(encoding="utf-8"))
    if metadata.get("owner_user_id") != owner_user_id:
        raise PermissionError("Import session does not belong to current user")
    return metadata


def _safe_source_name(name: str) -> str:
    candidate = Path(name).name
    if not candidate or candidate in {".", ".."}:
        return "source.txt"
    suffix = Path(candidate).suffix.lower()
    if suffix not in {".md", ".txt", ".json", ".jsonl"}:
        return f"{candidate}.txt"
    return candidate


def _unique_target(directory: Path, name: str) -> Path:
    target = directory / name
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    counter = 2
    while True:
        candidate = directory / f"{stem}-{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def _json_dumps(value: dict[str, Any]) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, indent=2)
