from pathlib import Path

from ai_memory.core.models import MemoryCandidate
from ai_memory.store.sqlite import SQLiteMemoryStore


def make_candidate() -> MemoryCandidate:
    return MemoryCandidate(
        uri="project://github.com/acme/app/commands",
        type="project_command",
        scope="project",
        content="Use pnpm test for tests.",
        summary="Test command is pnpm test.",
        confidence=0.91,
        risk="low",
        evidence="package.json scripts were checked",
        tags=("testing", "pnpm"),
        triggers=("test", "pnpm"),
        repo_id="github.com/acme/app",
        source_client="generic",
        session_id="sess_test",
        transcript_ref="raw/generic/sess_test.md",
    )


def test_create_memory_persists_record_source_version_and_fts(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()

    record = store.create_memory(make_candidate(), status="auto_approved", change_reason="test insert")

    loaded = store.get_memory(record.id)
    assert loaded is not None
    assert loaded.content == "Use pnpm test for tests."
    assert loaded.status == "auto_approved"

    sources = store.list_sources(record.id)
    assert len(sources) == 1
    assert sources[0]["evidence"] == "package.json scripts were checked"

    versions = store.list_versions(record.id)
    assert len(versions) == 1
    assert versions[0]["version"] == 1

    results = store.search("pnpm", limit=5)
    assert [item.id for item in results] == [record.id]


def test_append_source_rejects_mismatched_candidate(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()
    record = store.create_memory(make_candidate(), status="auto_approved", change_reason="test insert")
    mismatch = MemoryCandidate(
        uri=make_candidate().uri,
        type="project_command",
        scope="project",
        content="Use pnpm test for tests.",
        summary="Different summary.",
        confidence=0.91,
        risk="low",
        evidence="different source",
        repo_id="github.com/acme/app",
    )

    try:
        store.append_source(record.id, mismatch)
    except ValueError as error:
        assert "does not match target memory" in str(error)
    else:
        raise AssertionError("append_source should reject mismatched candidates")


def test_update_memory_creates_new_version_and_refreshes_search_index(tmp_path: Path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()
    record = store.create_memory(make_candidate(), status="auto_approved", change_reason="test insert")

    updated = store.update_memory(record.id, "Use pnpm test -- --runInBand for tests.", "command refined")

    assert updated.content == "Use pnpm test -- --runInBand for tests."
    loaded = store.get_memory(record.id)
    assert loaded is not None
    assert loaded.content == "Use pnpm test -- --runInBand for tests."
    versions = store.list_versions(record.id)
    assert [version["version"] for version in versions] == [1, 2]
    results = store.search("runInBand", limit=5)
    assert [item.id for item in results] == [record.id]
