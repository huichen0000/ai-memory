from pathlib import Path

from ai_memory.core.models import MemoryCandidate
from ai_memory.retrieval.assembler import assemble_context, hook_json
from ai_memory.retrieval.environment import detect_environment
from ai_memory.store.sqlite import SQLiteMemoryStore
from ai_memory.cli.main import run


def test_detect_environment_without_git(tmp_path: Path):
    env = detect_environment(tmp_path, client="generic", prompt="run tests")
    assert env["cwd"] == str(tmp_path)
    assert env["client"] == "generic"
    assert env["prompt"] == "run tests"
    assert env["repo_id"].startswith("local/")


def test_assemble_context_groups_memories(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()
    record = store.create_memory(
        MemoryCandidate(
            uri="project://local/demo/commands",
            type="project_command",
            scope="project",
            content="Use pytest for tests.",
            summary="Test command is pytest.",
            confidence=0.9,
            risk="low",
            evidence="user confirmed",
            tags=("testing",),
            triggers=("pytest",),
            repo_id="local/demo",
        ),
        status="auto_approved",
        change_reason="test",
    )
    context = assemble_context([record], title="Retrieved Memory")
    assert "# Retrieved Memory" in context
    assert "project://local/demo/commands" in context
    assert "Use pytest for tests." in context


def test_hook_json_contains_additional_context():
    payload = hook_json("SessionStart", "# Retrieved Memory\n- Use pytest")
    assert payload["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "Use pytest" in payload["hookSpecificOutput"]["additionalContext"]


def test_cli_add_search_and_context(tmp_path: Path, capsys):
    home = tmp_path / ".ai-memory"
    assert run(["init", "--home", str(home)]) == 0
    assert run([
        "add",
        "project://local/demo/commands",
        "Use pytest for tests.",
        "--home",
        str(home),
        "--type",
        "project_command",
        "--scope",
        "project",
    ]) == 0
    assert run(["search", "pytest", "--home", str(home)]) == 0
    search_output = capsys.readouterr().out
    assert "Use pytest for tests." in search_output
    assert run(["context", "--home", str(home), "--prompt", "run tests"]) == 0
    context_output = capsys.readouterr().out
    assert "Use pytest for tests." in context_output
