import json
from pathlib import Path

import pytest

from ai_memory.cli.main import run
from ai_memory.core.models import MemoryCandidate
from ai_memory.privacy.redactor import redact_secrets
from ai_memory.privacy.sensitive_paths import is_sensitive_path
from ai_memory.review.queue import ReviewQueue


def make_candidate() -> MemoryCandidate:
    return MemoryCandidate(
        uri="project://github.com/acme/app/testing",
        type="testing_rule",
        scope="project",
        content="Use pnpm test for tests.",
        summary="Test command is pnpm test.",
        confidence=0.93,
        risk="low",
        evidence="user confirmed",
    )


def test_redact_common_secrets():
    text = "Authorization: Bearer abcdef1234567890\nDATABASE_URL=postgres://user:pass@example.com/db"

    redacted = redact_secrets(text)

    assert "abcdef1234567890" not in redacted
    assert "user:pass" not in redacted
    assert "[REDACTED:BEARER_TOKEN]" in redacted
    assert "postgres://user:[REDACTED]@example.com/db" in redacted


def test_redact_bearer_token_with_plus_slash_equals():
    text = "Authorization: Bearer abc+/def=ghi=="

    redacted = redact_secrets(text)

    assert "abc+/def=ghi==" not in redacted
    assert redacted == "Authorization: Bearer [REDACTED:BEARER_TOKEN]"


def test_redact_api_key_password_and_private_key():
    text = "\n".join(
        [
            "api_key=secret-api-key",
            "password: super-secret",
            "-----BEGIN OPENSSH PRIVATE KEY-----",
            "private-key-body",
            "-----END OPENSSH PRIVATE KEY-----",
        ]
    )

    redacted = redact_secrets(text)

    assert "secret-api-key" not in redacted
    assert "super-secret" not in redacted
    assert "private-key-body" not in redacted
    assert "[REDACTED:API_KEY]" in redacted
    assert "[REDACTED:PASSWORD]" in redacted
    assert "[REDACTED:PRIVATE_KEY]" in redacted


def test_detect_sensitive_paths():
    assert is_sensitive_path(Path(".env"))
    assert is_sensitive_path(Path("/home/user/.ssh/id_ed25519"))
    assert is_sensitive_path(Path("credentials.json"))
    assert not is_sensitive_path(Path("docs/notes.md"))


def test_detect_sensitive_paths_case_insensitively():
    assert is_sensitive_path(Path(".ENV"))
    assert is_sensitive_path(Path("config/.ENV.production"))
    assert is_sensitive_path(Path("/home/user/.SSH/ID_RSA"))
    assert is_sensitive_path(Path("ID_RSA"))
    assert is_sensitive_path(Path("SECRET.PEM"))


def test_detect_common_credential_paths():
    assert is_sensitive_path(Path("service-account.json"))
    assert is_sensitive_path(Path("service_account.json"))
    assert is_sensitive_path(Path("client_secret.json"))
    assert is_sensitive_path(Path("oauth_token.json"))
    assert is_sensitive_path(Path("credentials.txt"))
    assert is_sensitive_path(Path("private_key.json"))
    assert is_sensitive_path(Path("private-key.txt"))
    assert is_sensitive_path(Path("secrets.json"))
    assert is_sensitive_path(Path(".netrc"))
    assert is_sensitive_path(Path(".npmrc"))
    assert is_sensitive_path(Path(".pypirc"))
    assert is_sensitive_path(Path("id_ecdsa"))
    assert is_sensitive_path(Path("id_dsa"))
    assert is_sensitive_path(Path("/home/user/.kube/config"))
    assert is_sensitive_path(Path("/home/user/.docker/config.json"))
    assert is_sensitive_path(Path("/home/user/.config/gh/hosts.yml"))
    assert is_sensitive_path(Path("/home/user/.azure/accessTokens.json"))
    assert is_sensitive_path(Path("/home/user/.config/gcloud/credentials.db"))


def test_review_queue_round_trip(tmp_path: Path):
    queue = ReviewQueue(tmp_path / "review-queue.jsonl")

    item = queue.enqueue(make_candidate(), reason="testing_rule requires review")
    pending = queue.list_pending()

    assert len(pending) == 1
    assert pending[0].id == item.id
    assert pending[0].candidate.type == "testing_rule"

    queue.mark(item.id, "approved")
    assert queue.list_pending() == []


def test_review_queue_persists_after_reopen(tmp_path: Path):
    path = tmp_path / "review-queue.jsonl"
    item = ReviewQueue(path).enqueue(make_candidate(), reason="testing_rule requires review")

    reopened = ReviewQueue(path)
    pending = reopened.list_pending()

    assert [entry.id for entry in pending] == [item.id]


def test_review_queue_mark_rejects_invalid_status(tmp_path: Path):
    queue = ReviewQueue(tmp_path / "review-queue.jsonl")
    item = queue.enqueue(make_candidate(), reason="testing_rule requires review")

    with pytest.raises(ValueError, match="Invalid review status"):
        queue.mark(item.id, "invalid")


def test_review_queue_raises_on_malformed_stored_status(tmp_path: Path):
    path = tmp_path / "review-queue.jsonl"
    item = ReviewQueue(path).enqueue(make_candidate(), reason="testing_rule requires review")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    rows[0]["status"] = "invalid"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid review status"):
        ReviewQueue(path).list_pending()

    assert item.id


def test_review_queue_mark_removes_terminal_items(tmp_path: Path):
    path = tmp_path / "review-queue.jsonl"
    queue = ReviewQueue(path)
    item = queue.enqueue(make_candidate(), reason="testing_rule requires review")

    queue.mark(item.id, "approved")

    assert queue.list_pending() == []
    assert "Use pnpm test for tests." not in path.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match=f"Unknown review id: {item.id}"):
        queue.get_pending(item.id)


def test_review_queue_mark_rewrites_without_leaving_temp_files(tmp_path: Path):
    path = tmp_path / "review-queue.jsonl"
    queue = ReviewQueue(path)
    item = queue.enqueue(make_candidate(), reason="testing_rule requires review")

    queue.mark(item.id, "approved")

    assert path.exists()
    assert sorted(file.name for file in tmp_path.iterdir()) == ["review-queue.jsonl"]


def test_cli_review_lists_empty_queue(tmp_path: Path, capsys):
    home = tmp_path / ".ai-memory"
    run(["init", "--home", str(home)])

    assert run(["review", "--home", str(home)]) == 0
    output = capsys.readouterr().out
    assert "No pending review items" in output


def test_cli_review_lists_pending_items(tmp_path: Path, capsys):
    home = tmp_path / ".ai-memory"
    item = ReviewQueue(home / "review-queue.jsonl").enqueue(make_candidate(), reason="testing_rule requires review")

    assert run(["review", "--home", str(home)]) == 0
    output = capsys.readouterr().out

    assert item.id in output
    assert "project://github.com/acme/app/testing" in output
    assert "testing_rule requires review" in output


def test_cli_review_approve_and_reject_use_configured_queue_path(tmp_path: Path, capsys):
    home = tmp_path / ".ai-memory"
    run(["init", "--home", str(home)])
    custom_queue = tmp_path / "queues" / "custom-review.jsonl"
    config_file = home / "config.yaml"
    config_text = config_file.read_text(encoding="utf-8")
    config_file.write_text(
        config_text.replace(f"review_queue: {home / 'review-queue.jsonl'}", f"review_queue: {custom_queue}"),
        encoding="utf-8",
    )
    approve_item = ReviewQueue(custom_queue).enqueue(make_candidate(), reason="testing_rule requires review")
    reject_item = ReviewQueue(custom_queue).enqueue(make_candidate(), reason="testing_rule requires review")

    assert run(["review", "--home", str(home)]) == 0
    review_output = capsys.readouterr().out
    assert approve_item.id in review_output
    assert reject_item.id in review_output

    assert run(["approve", approve_item.id, "--home", str(home)]) == 0
    assert run(["reject", reject_item.id, "--home", str(home)]) == 0
    output = capsys.readouterr().out

    assert f"Approved {approve_item.id}" in output
    assert f"Rejected {reject_item.id}" in output
    assert ReviewQueue(custom_queue).list_pending() == []


def test_cli_approve_rejects_invalid_review_candidate(tmp_path: Path, capsys):
    home = tmp_path / ".ai-memory"
    run(["init", "--home", str(home)])
    invalid = MemoryCandidate(
        uri="project://github.com/acme/app/testing",
        type="testing_rule",
        scope="global",
        content="Use pnpm test for tests.",
        summary="Test command is pnpm test.",
        confidence=0.93,
        risk="low",
        evidence="user confirmed",
    )
    item = ReviewQueue(home / "review-queue.jsonl").enqueue(invalid, reason="testing_rule requires review")

    assert run(["approve", item.id, "--home", str(home)]) == 2
    output = capsys.readouterr().out

    assert "candidate scope does not match URI namespace" in output
    assert [pending.id for pending in ReviewQueue(home / "review-queue.jsonl").list_pending()] == [item.id]


def test_cli_approve_writes_review_item_to_memory_store(tmp_path: Path, capsys):
    home = tmp_path / ".ai-memory"
    run(["init", "--home", str(home)])
    queue = ReviewQueue(home / "review-queue.jsonl")
    approve_item = queue.enqueue(make_candidate(), reason="testing_rule requires review")

    assert run(["approve", approve_item.id, "--home", str(home)]) == 0
    output = capsys.readouterr().out

    assert f"Approved {approve_item.id}" in output
    from ai_memory.store.sqlite import SQLiteMemoryStore

    store = SQLiteMemoryStore(home / "memory.db")
    records = store.search("pnpm", limit=10)
    assert len(records) == 1
    assert records[0].content == "Use pnpm test for tests."
    assert ReviewQueue(home / "review-queue.jsonl").list_pending() == []


def test_cli_approve_duplicate_same_uri_does_not_create_second_memory(tmp_path: Path, capsys):
    home = tmp_path / ".ai-memory"
    run(["init", "--home", str(home)])
    queue = ReviewQueue(home / "review-queue.jsonl")
    first = queue.enqueue(make_candidate(), reason="testing_rule requires review")
    second = queue.enqueue(make_candidate(), reason="testing_rule requires review")

    assert run(["approve", first.id, "--home", str(home)]) == 0
    assert run(["approve", second.id, "--home", str(home)]) == 0
    capsys.readouterr()

    from ai_memory.store.sqlite import SQLiteMemoryStore

    store = SQLiteMemoryStore(home / "memory.db")
    records = store.search("pnpm", limit=10)
    assert len(records) == 1
    assert len(store.list_sources(records[0].id)) == 2


def test_cli_approve_conflicting_uri_keeps_item_pending(tmp_path: Path, capsys):
    home = tmp_path / ".ai-memory"
    run(["init", "--home", str(home)])
    queue = ReviewQueue(home / "review-queue.jsonl")
    existing = queue.enqueue(make_candidate(), reason="testing_rule requires review")
    assert run(["approve", existing.id, "--home", str(home)]) == 0

    conflicting_candidate = make_candidate()
    conflicting_candidate = MemoryCandidate(
        uri=conflicting_candidate.uri,
        type=conflicting_candidate.type,
        scope=conflicting_candidate.scope,
        content="Use pytest for tests.",
        summary="Test command is pytest.",
        confidence=conflicting_candidate.confidence,
        risk=conflicting_candidate.risk,
        evidence="conflicting user confirmation",
    )
    conflict = queue.enqueue(conflicting_candidate, reason="testing_rule requires review")

    assert run(["approve", conflict.id, "--home", str(home)]) == 2
    output = capsys.readouterr().out

    assert "Conflicting memory already exists" in output
    assert [item.id for item in ReviewQueue(home / "review-queue.jsonl").list_pending()] == [conflict.id]


def test_cli_approve_and_reject_mark_existing_items(tmp_path: Path, capsys):
    home = tmp_path / ".ai-memory"
    run(["init", "--home", str(home)])
    queue = ReviewQueue(home / "review-queue.jsonl")
    approve_item = queue.enqueue(make_candidate(), reason="testing_rule requires review")
    reject_item = queue.enqueue(make_candidate(), reason="testing_rule requires review")

    assert run(["approve", approve_item.id, "--home", str(home)]) == 0
    assert run(["reject", reject_item.id, "--home", str(home)]) == 0
    output = capsys.readouterr().out

    assert f"Approved {approve_item.id}" in output
    assert f"Rejected {reject_item.id}" in output
    assert ReviewQueue(home / "review-queue.jsonl").list_pending() == []


def test_cli_approve_and_reject_report_missing_ids(tmp_path: Path, capsys):
    home = tmp_path / ".ai-memory"
    run(["init", "--home", str(home)])

    assert run(["approve", "rev_missing", "--home", str(home)]) == 2
    assert run(["reject", "rev_missing", "--home", str(home)]) == 2
    output = capsys.readouterr().out

    assert output.count("Unknown review id: rev_missing") == 2
