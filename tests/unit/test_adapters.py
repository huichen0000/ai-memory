from pathlib import Path

from ai_memory.adapters.claude_code import ClaudeCodeAdapter
from ai_memory.adapters.codex_cli import CodexCliAdapter
from ai_memory.adapters.gemini_cli import GeminiCliAdapter
from ai_memory.wrappers.aiwrap import build_wrapped_prompt


def test_claude_adapter_discovers_project_jsonl(tmp_path: Path):
    projects = tmp_path / ".claude" / "projects" / "demo"
    projects.mkdir(parents=True)
    session = projects / "session.jsonl"
    session.write_text('{"type":"user","message":"hello"}\n', encoding="utf-8")

    adapter = ClaudeCodeAdapter(home=tmp_path)
    sources = adapter.discover()

    assert sources == [session]


def test_codex_and_gemini_adapters_return_empty_when_missing(tmp_path: Path):
    assert CodexCliAdapter(home=tmp_path).discover() == []
    assert GeminiCliAdapter(home=tmp_path).discover() == []


def test_build_wrapped_prompt_prepends_context():
    prompt = build_wrapped_prompt("# Retrieved Memory\n- Use pytest", "fix tests")

    assert prompt.startswith("# Retrieved Memory")
    assert prompt.endswith("fix tests")
