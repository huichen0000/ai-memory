from pathlib import Path

from ai_memory.core.models import MemoryCandidate
from ai_memory.privacy.redactor import redact_secrets
from ai_memory.privacy.sensitive_paths import is_sensitive_path
from ai_memory.review.queue import ReviewQueue


def test_redact_common_secrets():
    text = "Authorization: Bearer abcdef1234567890\nDATABASE_URL=postgres://user:pass@example.com/db"

    redacted = redact_secrets(text)

    assert "abcdef1234567890" not in redacted
    assert "user:pass" not in redacted
    assert "[REDACTED:BEARER_TOKEN]" in redacted
    assert "postgres://user:[REDACTED]@example.com/db" in redacted


def test_detect_sensitive_paths():
    assert is_sensitive_path(Path(".env"))
    assert is_sensitive_path(Path("/home/user/.ssh/id_ed25519"))
    assert is_sensitive_path(Path("credentials.json"))
    assert not is_sensitive_path(Path("docs/notes.md"))


def test_review_queue_round_trip(tmp_path: Path):
    candidate = MemoryCandidate(
        uri="project://github.com/acme/app/testing",
        type="testing_rule",
        scope="project",
        content="Use pnpm test for tests.",
        summary="Test command is pnpm test.",
        confidence=0.93,
        risk="low",
        evidence="user confirmed",
    )
    queue = ReviewQueue(tmp_path / "review-queue.jsonl")

    item = queue.enqueue(candidate, reason="testing_rule requires review")
    pending = queue.list_pending()

    assert len(pending) == 1
    assert pending[0].id == item.id
    assert pending[0].candidate.type == "testing_rule"

    queue.mark(item.id, "approved")
    assert queue.list_pending() == []
