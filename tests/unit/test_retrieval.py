from pathlib import Path

from ai_memory.core.models import MemoryCandidate
from ai_memory.retrieval.assembler import assemble_context, hook_json
from ai_memory.mcp.tools import memory_context
from ai_memory.retrieval.environment import _repo_id_from_remote, detect_environment
from ai_memory.store.sqlite import SQLiteMemoryStore
from ai_memory.cli.main import run


def test_detect_environment_without_git(tmp_path: Path):
    env = detect_environment(tmp_path, client="generic", prompt="run tests")
    assert env["cwd"] == str(tmp_path)
    assert env["client"] == "generic"
    assert env["prompt"] == "run tests"
    assert env["repo_id"].startswith("local/")
    assert env["relative_path"] is None


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


def test_cli_add_rejects_scope_uri_mismatch(tmp_path: Path, capsys):
    home = tmp_path / ".ai-memory"
    assert run(["init", "--home", str(home)]) == 0

    exit_code = run([
        "add",
        "project://local/demo/commands",
        "Use pytest for tests.",
        "--home",
        str(home),
        "--type",
        "project_command",
        "--scope",
        "global",
    ])
    output = capsys.readouterr().out

    assert exit_code == 2
    assert "candidate scope does not match URI namespace" in output


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


def test_cli_search_scopes_results_to_detected_environment(tmp_path: Path, capsys, monkeypatch):
    home = tmp_path / ".ai-memory"
    cwd = tmp_path / "repo"
    cwd.mkdir()
    assert run(["init", "--home", str(home)]) == 0
    store = SQLiteMemoryStore(home / "memory.db")
    store.initialize()
    local_repo = detect_environment(cwd, client="cli", prompt="pytest")["repo_id"]
    store.create_memory(
        MemoryCandidate(
            uri="project://other/repo/commands",
            type="project_command",
            scope="project",
            content="Other repo pytest memory.",
            summary="Other repo pytest.",
            confidence=0.99,
            risk="low",
            evidence="test",
            tags=("pytest",),
            triggers=("pytest",),
            repo_id="other/repo",
        ),
        status="approved",
        change_reason="test",
    )
    store.create_memory(
        MemoryCandidate(
            uri="project://local/detected/commands",
            type="project_command",
            scope="project",
            content="Local repo pytest memory.",
            summary="Local repo pytest.",
            confidence=0.8,
            risk="low",
            evidence="test",
            tags=("pytest",),
            triggers=("pytest",),
            repo_id=local_repo,
        ),
        status="approved",
        change_reason="test",
    )
    monkeypatch.chdir(cwd)

    assert run(["search", "pytest", "--home", str(home)]) == 0
    search_output = capsys.readouterr().out

    assert "Local repo pytest memory." in search_output
    assert "Other repo pytest memory." not in search_output


def test_cli_search_and_context_exclude_unapproved_memories(tmp_path: Path, capsys):
    home = tmp_path / ".ai-memory"
    assert run(["init", "--home", str(home)]) == 0
    store = SQLiteMemoryStore(home / "memory.db")
    store.initialize()
    repo_id = detect_environment(Path.cwd(), client="cli", prompt="pytest")["repo_id"]
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
                repo_id=repo_id,
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


def test_memory_context_does_not_recall_same_branch_from_other_repo(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()
    local_record = store.create_memory(
        MemoryCandidate(
            uri="project://local/demo/testing",
            type="testing_rule",
            scope="project",
            content="Local project baseline memory.",
            summary="Local project baseline.",
            confidence=0.8,
            risk="low",
            evidence="test",
            repo_id="local/demo",
            branch="main",
        ),
        status="approved",
        change_reason="test",
    )
    other_record = store.create_memory(
        MemoryCandidate(
            uri="branch://other/repo/main/testing",
            type="testing_rule",
            scope="branch",
            content="Other project branch memory.",
            summary="Other project branch.",
            confidence=0.99,
            risk="low",
            evidence="test",
            repo_id="other/repo",
            branch="main",
        ),
        status="approved",
        change_reason="test",
    )

    context = memory_context(
        store=store,
        prompt="unrelated",
        max_items=5,
        environment={"repo_id": "local/demo", "branch": "main", "cwd": str(tmp_path)},
    )

    ids = [item["id"] for item in context["items"]]
    assert local_record.id in ids
    assert other_record.id not in ids


def test_cli_context_uses_detected_environment_for_project_memory(tmp_path: Path, capsys, monkeypatch):
    home = tmp_path / ".ai-memory"
    cwd = tmp_path / "repo"
    cwd.mkdir()
    repo_id = detect_environment(cwd, client="cli", prompt="unrelated")["repo_id"]
    run(["init", "--home", str(home)])
    store = SQLiteMemoryStore(home / "memory.db")
    store.initialize()
    store.create_memory(
        MemoryCandidate(
            uri="project://local/detected/testing",
            type="testing_rule",
            scope="project",
            content="Detected project memory is loaded by environment.",
            summary="Detected project memory.",
            confidence=0.8,
            risk="low",
            evidence="test",
            repo_id=repo_id,
        ),
        status="approved",
        change_reason="test",
    )
    monkeypatch.chdir(cwd)

    assert run(["context", "--home", str(home), "--prompt", "unrelated"]) == 0
    context_output = capsys.readouterr().out

    assert "Detected project memory is loaded by environment." in context_output


def test_cli_context_uses_path_for_path_scoped_memory(tmp_path: Path, capsys, monkeypatch):
    home = tmp_path / ".ai-memory"
    cwd = tmp_path / "repo"
    target = cwd / "src" / "api" / "routes.py"
    target.parent.mkdir(parents=True)
    target.write_text("", encoding="utf-8")
    repo_id = detect_environment(cwd, client="cli", prompt="fixtures")["repo_id"]
    run(["init", "--home", str(home)])
    store = SQLiteMemoryStore(home / "memory.db")
    store.initialize()
    store.create_memory(
        MemoryCandidate(
            uri="path://local/detected/src/api/testing",
            type="testing_rule",
            scope="path",
            content="Detected path memory is loaded by path.",
            summary="Detected path memory.",
            confidence=0.8,
            risk="low",
            evidence="test",
            repo_id=repo_id,
            path_glob="src/api/**/*.py",
        ),
        status="approved",
        change_reason="test",
    )
    monkeypatch.chdir(cwd)

    assert run(["context", "--home", str(home), "--prompt", "fixtures", "--path", "src/api/routes.py"]) == 0
    context_output = capsys.readouterr().out

    assert "Detected path memory is loaded by path." in context_output


def test_memory_context_prioritizes_scope_and_trigger_matches(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()
    global_record = store.create_memory(
        MemoryCandidate(
            uri="global://user/testing",
            type="testing_rule",
            scope="global",
            content="Generic pytest guidance.",
            summary="Generic pytest guidance.",
            confidence=0.99,
            risk="low",
            evidence="test",
            tags=("pytest",),
            triggers=("pytest",),
        ),
        status="approved",
        change_reason="test",
    )
    project_record = store.create_memory(
        MemoryCandidate(
            uri="project://local/demo/testing",
            type="testing_rule",
            scope="project",
            content="Local demo uses pytest markers.",
            summary="Local demo pytest markers.",
            confidence=0.8,
            risk="low",
            evidence="test",
            tags=("testing",),
            triggers=("integration",),
            repo_id="local/demo",
        ),
        status="approved",
        change_reason="test",
    )

    context = memory_context(
        store=store,
        prompt="run integration tests",
        max_items=5,
        environment={"repo_id": "local/demo", "branch": None, "cwd": str(tmp_path)},
    )

    assert [item["id"] for item in context["items"]][:2] == [project_record.id, global_record.id]


def test_memory_context_ranks_contextual_records_before_limiting(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()
    for index in range(10):
        store.create_memory(
            MemoryCandidate(
                uri=f"project://local/demo/filler/{index}",
                type="project_command",
                scope="project",
                content=f"Filler command {index}.",
                summary=f"Filler command {index}.",
                confidence=0.99,
                risk="low",
                evidence="test",
                repo_id="local/demo",
            ),
            status="approved",
            change_reason="test",
        )
    important = store.create_memory(
        MemoryCandidate(
            uri="branch://local/demo/main/important",
            type="project_command",
            scope="branch",
            content="Run the branch-specific checks.",
            summary="Branch-specific checks.",
            confidence=0.6,
            risk="low",
            evidence="test",
            repo_id="local/demo",
            branch="main",
        ),
        status="approved",
        change_reason="test",
    )

    context = memory_context(
        store=store,
        prompt="unrelated",
        max_items=3,
        environment={"repo_id": "local/demo", "branch": "main", "cwd": str(tmp_path)},
    )

    assert context["items"][0]["id"] == important.id


def test_memory_context_uses_explicit_triggers_not_only_content(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()
    matched = store.create_memory(
        MemoryCandidate(
            uri="project://local/demo/commands",
            type="project_command",
            scope="project",
            content="Use the standard test command.",
            summary="Standard test command.",
            confidence=0.7,
            risk="low",
            evidence="test",
            triggers=("contract",),
            repo_id="local/demo",
        ),
        status="approved",
        change_reason="test",
    )
    unmatched = store.create_memory(
        MemoryCandidate(
            uri="project://local/demo/generic",
            type="project_command",
            scope="project",
            content="Use the generic test command.",
            summary="Generic test command.",
            confidence=0.99,
            risk="low",
            evidence="test",
            repo_id="local/demo",
        ),
        status="approved",
        change_reason="test",
    )

    context = memory_context(
        store=store,
        prompt="contract checks",
        max_items=5,
        environment={"repo_id": "local/demo", "branch": None, "cwd": str(tmp_path)},
    )

    assert [item["id"] for item in context["items"]][:2] == [matched.id, unmatched.id]


def test_memory_context_omits_path_scope_without_relative_path(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()
    path_record = store.create_memory(
        MemoryCandidate(
            uri="path://local/demo/docs/testing",
            type="testing_rule",
            scope="path",
            content="Docs tests use markdown fixtures.",
            summary="Docs test fixtures.",
            confidence=0.99,
            risk="low",
            evidence="test",
            repo_id="local/demo",
            path_glob="docs/**/*.md",
        ),
        status="approved",
        change_reason="test",
    )

    context = memory_context(
        store=store,
        prompt="fixtures",
        max_items=5,
        environment={"repo_id": "local/demo", "branch": None, "cwd": str(tmp_path)},
    )

    assert path_record.id not in [item["id"] for item in context["items"]]


def test_memory_context_filters_path_scope_by_relative_path(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()
    matched = store.create_memory(
        MemoryCandidate(
            uri="path://local/demo/src/api/testing",
            type="testing_rule",
            scope="path",
            content="API tests use contract fixtures.",
            summary="API test fixtures.",
            confidence=0.8,
            risk="low",
            evidence="test",
            repo_id="local/demo",
            path_glob="src/api/**/*.py",
        ),
        status="approved",
        change_reason="test",
    )
    unmatched = store.create_memory(
        MemoryCandidate(
            uri="path://local/demo/docs/testing",
            type="testing_rule",
            scope="path",
            content="Docs tests use markdown fixtures.",
            summary="Docs test fixtures.",
            confidence=0.99,
            risk="low",
            evidence="test",
            repo_id="local/demo",
            path_glob="docs/**/*.md",
        ),
        status="approved",
        change_reason="test",
    )

    context = memory_context(
        store=store,
        prompt="fixtures",
        max_items=5,
        environment={
            "repo_id": "local/demo",
            "branch": None,
            "cwd": str(tmp_path),
            "relative_path": "src/api/routes.py",
        },
    )

    ids = [item["id"] for item in context["items"]]
    assert matched.id in ids
    assert unmatched.id not in ids
