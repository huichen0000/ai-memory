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
