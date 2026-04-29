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
    config = AppConfig(
        home=home,
        store_path=home / "memory.db",
        raw_dir=home / "raw",
        log_dir=home / "logs",
        review_queue_path=home / "review-queue.jsonl",
        extractor_provider=None,
        extractor_command=None,
        max_input_chars=60000,
        retrieval_max_items=12,
        retrieval_max_chars=6000,
        auto_write_confidence=0.85,
        redact_secrets=True,
        confirm_sensitive_sources=True,
    )
    config.home.mkdir(parents=True, exist_ok=True)
    config.raw_dir.mkdir(parents=True, exist_ok=True)
    config.log_dir.mkdir(parents=True, exist_ok=True)
    config.review_queue_path.touch(exist_ok=True)
    config_file = config.home / "config.yaml"
    config_file.write_text(yaml.safe_dump(config_to_dict(config), sort_keys=False), encoding="utf-8")
    return config
