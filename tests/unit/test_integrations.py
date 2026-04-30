import json
from pathlib import Path

from ai_memory.cli.main import run as cli_run
from ai_memory.integrations.snippets import claude_code_settings_snippet, install_instructions, integration_status


def test_claude_code_settings_snippet_uses_session_start_hook(tmp_path: Path):
    snippet = claude_code_settings_snippet(tmp_path / ".ai-memory")

    hook = snippet["hooks"]["SessionStart"][0]["hooks"][0]

    assert hook["type"] == "command"
    assert "ai-memory context" in hook["command"]
    assert "--format hook-json" in hook["command"]
    assert "--event SessionStart" in hook["command"]

    prompt_hook = snippet["hooks"]["UserPromptSubmit"][0]["hooks"][0]
    assert "--event UserPromptSubmit" in prompt_hook["command"]
    assert "--stdin-json-prompt" in prompt_hook["command"]


def test_claude_code_install_instructions_do_not_claim_to_edit_settings(tmp_path: Path):
    text = install_instructions("claude-code", tmp_path / ".ai-memory")

    assert "ccswitch-safe" in text
    assert "no settings file was modified" in text
    assert "SessionStart" in text


def test_wrapper_install_instructions_for_codex(tmp_path: Path):
    text = install_instructions("codex-cli", tmp_path / ".ai-memory")

    assert "aiwrap codex" in text
    assert str(tmp_path / ".ai-memory") in text


def test_integration_status_reports_safe_modes(tmp_path: Path):
    claude = integration_status("claude-code", tmp_path / ".ai-memory")
    codex = integration_status("codex-cli", tmp_path / ".ai-memory")

    assert claude.status == "manual-snippet"
    assert codex.status == "wrapper-available"


def test_cli_integrate_status_lists_clients(tmp_path: Path, capsys):
    assert cli_run(["integrate", "status", "--home", str(tmp_path / ".ai-memory")]) == 0

    out = capsys.readouterr().out
    assert "claude-code" in out
    assert "codex-cli" in out
    assert "gemini-cli" in out


def test_cli_integrate_install_claude_code_prints_json_snippet(tmp_path: Path, capsys):
    assert cli_run(["integrate", "install", "claude-code", "--home", str(tmp_path / ".ai-memory")]) == 0

    out = capsys.readouterr().out
    assert "ccswitch-safe" in out
    json_start = out.index("{")
    snippet = json.loads(out[json_start:])
    assert snippet["hooks"]["SessionStart"][0]["hooks"][0]["type"] == "command"


def test_cli_integrate_install_rejects_unknown_client(tmp_path: Path):
    try:
        cli_run(["integrate", "install", "unknown", "--home", str(tmp_path / ".ai-memory")])
    except SystemExit as error:
        assert error.code == 2
    else:
        raise AssertionError("unknown client should exit")
