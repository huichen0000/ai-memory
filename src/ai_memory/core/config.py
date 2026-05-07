from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import yaml


DEFAULT_EXTRACTOR_SETTINGS = {
    "mode": "heuristic",
    "base_url": "https://api.openai.com/v1",
    "api_key": "",
    "model": "",
    "prefilter": True,
    "llm_only_if_heuristic_empty": True,
    "cache": True,
}


@dataclass(frozen=True)
class AppConfig:
    home: Path
    store_path: Path
    raw_dir: Path
    log_dir: Path
    review_queue_path: Path
    extractor_provider: str | None
    extractor_command: str | Sequence[str] | None
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
        extractor_provider="command",
        extractor_command=_default_extractor_command(),
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


def _default_extractor_command() -> list[str]:
    return [sys.executable, str(Path(__file__).resolve().parents[3] / "scripts" / "extractor.py")]


def _config_for_home(home: Path) -> AppConfig:
    return AppConfig(
        home=home,
        store_path=home / "memory.db",
        raw_dir=home / "raw",
        log_dir=home / "logs",
        review_queue_path=home / "review-queue.jsonl",
        extractor_provider="command",
        extractor_command=_default_extractor_command(),
        max_input_chars=60000,
        retrieval_max_items=12,
        retrieval_max_chars=6000,
        auto_write_confidence=0.85,
        redact_secrets=True,
        confirm_sensitive_sources=True,
    )


def _resolve_config_path(home: Path, value: object, default: Path) -> Path:
    if not isinstance(value, str) or not value.strip():
        return default
    path = Path(value)
    return path if path.is_absolute() else home / path


def _resolve_extractor_command(value: object, default: str | Sequence[str] | None) -> str | Sequence[str] | None:
    if isinstance(value, str) and value.strip():
        return value
    if isinstance(value, list) and all(isinstance(item, str) and item for item in value):
        return value
    return default


def _ensure_home_artifacts(config: AppConfig) -> None:
    config.home.mkdir(parents=True, exist_ok=True)
    config.raw_dir.mkdir(parents=True, exist_ok=True)
    config.log_dir.mkdir(parents=True, exist_ok=True)
    config.review_queue_path.parent.mkdir(parents=True, exist_ok=True)
    config.review_queue_path.touch(exist_ok=True)


def write_extractor_settings(
    home: Path,
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    mode: str | None = None,
) -> None:
    settings = dict(DEFAULT_EXTRACTOR_SETTINGS)
    if base_url is not None:
        settings["base_url"] = base_url
    if api_key is not None:
        settings["api_key"] = api_key
    if model is not None:
        settings["model"] = model
    if mode is not None:
        settings["mode"] = mode
    (home / "extractor.json").write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_config(home: Path) -> AppConfig:
    config_file = home / "config.yaml"
    if not config_file.exists():
        return init_home(home)

    defaults = _config_for_home(home)
    data = yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        data = {}
    store = data.get("store") if isinstance(data.get("store"), dict) else {}
    paths = data.get("paths") if isinstance(data.get("paths"), dict) else {}
    extractor = data.get("extractor") if isinstance(data.get("extractor"), dict) else {}
    retrieval = data.get("retrieval") if isinstance(data.get("retrieval"), dict) else {}
    policy = data.get("policy") if isinstance(data.get("policy"), dict) else {}
    privacy = data.get("privacy") if isinstance(data.get("privacy"), dict) else {}

    config = AppConfig(
        home=home,
        store_path=_resolve_config_path(home, store.get("path"), defaults.store_path),
        raw_dir=_resolve_config_path(home, paths.get("raw_dir"), defaults.raw_dir),
        log_dir=_resolve_config_path(home, paths.get("log_dir"), defaults.log_dir),
        review_queue_path=_resolve_config_path(home, paths.get("review_queue"), defaults.review_queue_path),
        extractor_provider=extractor.get("provider") if isinstance(extractor.get("provider"), str) else defaults.extractor_provider,
        extractor_command=_resolve_extractor_command(extractor.get("command"), defaults.extractor_command),
        max_input_chars=int(extractor.get("max_input_chars", defaults.max_input_chars)),
        retrieval_max_items=int(retrieval.get("max_items", defaults.retrieval_max_items)),
        retrieval_max_chars=int(retrieval.get("max_chars", defaults.retrieval_max_chars)),
        auto_write_confidence=float(policy.get("auto_write_confidence", defaults.auto_write_confidence)),
        redact_secrets=bool(privacy.get("redact_secrets", defaults.redact_secrets)),
        confirm_sensitive_sources=bool(privacy.get("confirm_sensitive_sources", defaults.confirm_sensitive_sources)),
    )
    _ensure_home_artifacts(config)
    return config


def init_home(
    home: Path,
    *,
    extractor_base_url: str | None = None,
    extractor_api_key: str | None = None,
    extractor_model: str | None = None,
    extractor_mode: str | None = None,
) -> AppConfig:
    config = _config_for_home(home)
    _ensure_home_artifacts(config)
    config_file = config.home / "config.yaml"
    config_file.write_text(yaml.safe_dump(config_to_dict(config), sort_keys=False), encoding="utf-8")
    extractor_settings_path = config.home / "extractor.json"
    has_extractor_overrides = any(
        value is not None for value in (extractor_base_url, extractor_api_key, extractor_model, extractor_mode)
    )
    if has_extractor_overrides or not extractor_settings_path.exists():
        write_extractor_settings(
            config.home,
            base_url=extractor_base_url,
            api_key=extractor_api_key,
            model=extractor_model,
            mode=extractor_mode,
        )
    return config
