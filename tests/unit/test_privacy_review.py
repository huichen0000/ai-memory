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


def test_cli_approve_and_reject_mark_existing_items(tmp_path: Path, capsys):
    home = tmp_path / ".ai-memory"
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
