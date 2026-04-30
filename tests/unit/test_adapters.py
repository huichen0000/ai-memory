import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

from ai_memory.adapters.claude_code import ClaudeCodeAdapter
from ai_memory.adapters.codex_cli import CodexCliAdapter
from ai_memory.adapters.gemini_cli import GeminiCliAdapter
from ai_memory.cli.main import run as cli_run
from ai_memory.wrappers.aiwrap import build_wrapped_prompt, run as aiwrap_run


def test_claude_adapter_discovers_project_jsonl(tmp_path: Path):
    projects = tmp_path / ".claude" / "projects" / "demo"
    projects.mkdir(parents=True)
    session = projects / "session.jsonl"
    session.write_text('{"type":"user","message":"hello"}\n', encoding="utf-8")

    adapter = ClaudeCodeAdapter(home=tmp_path)
    sources = adapter.discover()

    assert sources == [session]


def test_claude_normalize_redacts_secret_content(tmp_path: Path):
    session = tmp_path / "session.jsonl"
    session.write_text(
        '{"type":"user","message":"api_key=secret-value"}\n'
        '{"type":"assistant","message":{"text":"password=hunter2"}}\n'
        '{"role":"user","content":["Bearer token-value"]}\n',
        encoding="utf-8",
    )

    transcript = ClaudeCodeAdapter(home=tmp_path).normalize(session)
    contents = "\n".join(message.content for message in transcript.messages)

    assert "secret-value" not in contents
    assert "hunter2" not in contents
    assert "token-value" not in contents
    assert "[REDACTED:API_KEY]" in contents
    assert "[REDACTED:PASSWORD]" in contents
    assert "[REDACTED:BEARER_TOKEN]" in contents


def test_claude_normalize_skips_malformed_jsonl_and_preserves_valid_messages(tmp_path: Path):
    session = tmp_path / "session.jsonl"
    session.write_text(
        '{"type":"user","message":"before"}\n'
        '{this is not json}\n'
        '{"type":"assistant","message":"after"}\n',
        encoding="utf-8",
    )

    transcript = ClaudeCodeAdapter(home=tmp_path).normalize(session)

    assert [message.content for message in transcript.messages] == ["before", "after"]


def test_codex_and_gemini_adapters_return_empty_when_missing(tmp_path: Path):
    assert CodexCliAdapter(home=tmp_path).discover() == []
    assert GeminiCliAdapter(home=tmp_path).discover() == []


def test_codex_discovery_filters_hidden_binary_and_wrong_suffix_files(tmp_path: Path):
    sessions = tmp_path / ".codex" / "sessions"
    hidden_dir = sessions / ".cache"
    hidden_dir.mkdir(parents=True)
    valid = sessions / "session.jsonl"
    valid.write_text("{}\n", encoding="utf-8")
    (sessions / ".hidden.jsonl").write_text("{}\n", encoding="utf-8")
    (sessions / "binary.bin").write_bytes(b"\x00\x01")
    (hidden_dir / "nested.jsonl").write_text("{}\n", encoding="utf-8")

    assert CodexCliAdapter(home=tmp_path).discover() == [valid]


def test_gemini_discovery_filters_wrong_suffix_files(tmp_path: Path):
    root = tmp_path / ".gemini"
    root.mkdir()
    valid = root / "session.md"
    valid.write_text("hello", encoding="utf-8")
    (root / "session.bin").write_bytes(b"\x00\x01")

    assert GeminiCliAdapter(home=tmp_path).discover() == [valid]


def test_cli_discover_prints_sources(tmp_path: Path, capsys):
    projects = tmp_path / ".claude" / "projects" / "demo"
    projects.mkdir(parents=True)
    session = projects / "session.jsonl"
    session.write_text("{}\n", encoding="utf-8")

    assert cli_run(["discover", "--client", "claude-code", "--home", str(tmp_path)]) == 0

    assert str(session) in capsys.readouterr().out


def test_cli_discover_rejects_unsupported_client(tmp_path: Path):
    try:
        cli_run(["discover", "--client", "unknown", "--home", str(tmp_path)])
    except SystemExit as error:
        assert error.code == 2
    else:
        raise AssertionError("unsupported client should exit")


def test_build_wrapped_prompt_prepends_context():
    prompt = build_wrapped_prompt("# Retrieved Memory\n- Use pytest", "fix tests")

    assert prompt.startswith("# Retrieved Memory")
    assert prompt.endswith("fix tests")


def test_aiwrap_run_preserves_client_args_before_wrapped_prompt():
    completed = subprocess.CompletedProcess(args=[], returncode=0)
    with patch("ai_memory.wrappers.aiwrap.subprocess.run", return_value=completed) as run_mock:
        result = aiwrap_run(["claude", "--model", "sonnet", "--", "fix tests"])

    assert result == 0
    run_mock.assert_called_once_with(
        ["claude", "--model", "sonnet", build_wrapped_prompt("", "fix tests")],
        check=False,
    )


def test_aiwrap_run_requires_prompt():
    with patch("ai_memory.wrappers.aiwrap.subprocess.run", Mock()) as run_mock:
        try:
            aiwrap_run(["claude", "--model", "sonnet"])
        except SystemExit as error:
            assert error.code == 2
        else:
            raise AssertionError("missing prompt should exit")

    run_mock.assert_not_called()


def test_aiwrap_run_returns_subprocess_return_code():
    completed = subprocess.CompletedProcess(args=[], returncode=17)
    with patch("ai_memory.wrappers.aiwrap.subprocess.run", return_value=completed):
        assert aiwrap_run(["claude", "--", "fix tests"]) == 17
