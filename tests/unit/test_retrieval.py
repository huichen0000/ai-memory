from pathlib import Path

from ai_memory.core.models import MemoryCandidate
from ai_memory.retrieval.assembler import assemble_context, hook_json
from ai_memory.retrieval.environment import _repo_id_from_remote, detect_environment
from ai_memory.store.sqlite import SQLiteMemoryStore
from ai_memory.cli.main import run


def test_detect_environment_without_git(tmp_path: Path):
    env = detect_environment(tmp_path, client="generic", prompt="run tests")
    assert env["cwd"] == str(tmp_path)
    assert env["client"] == "generic"
    assert env["prompt"] == "run tests"
    assert env["repo_id"].startswith("local/")


def test_repo_id_from_remote_normalizes_url_forms_without_credentials():
    assert _repo_id_from_remote("https://github.com/org/repo.git") == "github.com/org/repo"
    assert _repo_id_from_remote("ssh://git@github.com/org/repo.git") == "github.com/org/repo"
    assert _repo_id_from_remote("git@github.com:org/repo.git") == "github.com/org/repo"
    assert _repo_id_from_remote("https://github.com/org/repo.git/") == "github.com/org/repo"
    assert _repo_id_from_remote("https://user:token@github.com/org/repo.git") == "github.com/org/repo"


def test_assemble_context_empty_records_mentions_approved_memory():
    context = assemble_context([], title="Retrieved Memory")

    assert "No relevant approved memory found" in context


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


def test_cli_search_and_context_ignore_unsafe_query_punctuation(tmp_path: Path, capsys):
    home = tmp_path / ".ai-memory"
    assert run(["init", "--home", str(home)]) == 0
    assert run([
        "add",
        "project://local/demo/commands",
        "Use pytest for tests.",
        "--home",
        str(home),
    ]) == 0

    assert run(["search", "repo:pytest?", "--home", str(home)]) == 0
    search_output = capsys.readouterr().out
    assert "Use pytest for tests." in search_output

    assert run(["context", "--home", str(home), "--prompt", '"pytest -k unit']) == 0
    context_output = capsys.readouterr().out
    assert "Use pytest for tests." in context_output


def test_cli_context_caps_ranked_multi_token_results(tmp_path: Path, capsys):
    home = tmp_path / ".ai-memory"
    assert run(["init", "--home", str(home)]) == 0
    for index in range(12):
        assert run([
            "add",
            f"project://local/demo/pytest/{index}",
            f"Use pytest command {index}.",
            "--home",
            str(home),
        ]) == 0
    assert run([
        "add",
        "project://local/demo/marker/extra",
        "Use marker command extra.",
        "--home",
        str(home),
    ]) == 0
    capsys.readouterr()

    assert run(["context", "--home", str(home), "--prompt", "pytest marker"]) == 0
    context_output = capsys.readouterr().out
    assert context_output.count("## project://local/demo/") == 12


def test_cli_search_and_context_exclude_unapproved_memories(tmp_path: Path, capsys):
    home = tmp_path / ".ai-memory"
    assert run(["init", "--home", str(home)]) == 0
    store = SQLiteMemoryStore(home / "memory.db")
    store.initialize()
    for status in ("approved", "proposed", "rejected"):
        store.create_memory(
            MemoryCandidate(
                uri=f"project://local/demo/{status}",
                type="project_command",
                scope="project",
                content=f"{status} pytest memory",
                summary=f"{status} pytest memory",
                confidence=0.9,
                risk="low",
                evidence="test",
                tags=("pytest",),
                triggers=("pytest",),
                repo_id="local/demo",
            ),
            status=status,
            change_reason="test",
        )

    assert run(["search", "pytest", "--home", str(home)]) == 0
    search_output = capsys.readouterr().out
    assert "approved pytest memory" in search_output
    assert "proposed pytest memory" not in search_output
    assert "rejected pytest memory" not in search_output

    assert run(["context", "--home", str(home), "--prompt", "pytest"]) == 0
    context_output = capsys.readouterr().out
    assert "approved pytest memory" in context_output
    assert "proposed pytest memory" not in context_output
    assert "rejected pytest memory" not in context_output
