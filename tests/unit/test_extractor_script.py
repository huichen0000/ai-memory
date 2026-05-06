import importlib.util
import json
from pathlib import Path


def load_extractor_module():
    path = Path("scripts/extractor.py")
    spec = importlib.util.spec_from_file_location("ai_memory_extractor_script", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def transcript_with_secret() -> dict[str, object]:
    return {
        "client": "generic",
        "source_path": "/Users/example/private/project/chat.md",
        "repo_id": "github.com/acme/private",
        "branch": "main",
        "session_id": "session-secret-id",
        "messages": [
            {"role": "user", "content": "api_key=secret-value\nRemember to use pytest for tests."},
        ],
    }


def test_extractor_defaults_to_local_heuristics(monkeypatch):
    extractor = load_extractor_module()
    calls = []
    monkeypatch.setattr(extractor, "extract_with_llm", lambda transcript, settings: calls.append(transcript) or [])

    candidates = extractor.extract_candidates(transcript_with_secret())

    assert calls == []
    assert candidates
    assert candidates[0]["type"] in {"project_command", "pitfall"}


def test_extracted_candidates_minimize_durable_provenance():
    extractor = load_extractor_module()

    candidates = extractor.extract_candidates(transcript_with_secret())

    assert candidates
    for candidate in candidates:
        assert candidate.get("session_id") != "session-secret-id"
        assert candidate.get("transcript_ref") == "chat.md"
        assert "/Users/example/private/project/chat.md" not in json.dumps(candidate)


def test_llm_prompt_redacts_transcript_and_minimizes_metadata():
    extractor = load_extractor_module()

    prompt = extractor.build_llm_prompt(transcript_with_secret(), {})

    assert "secret-value" not in prompt
    assert "[REDACTED:API_KEY]" in prompt
    assert "/Users/example/private/project/chat.md" not in prompt
    assert "session-secret-id" not in prompt
    metadata_text = prompt.split("Metadata:\n", 1)[1].split("\n\nTranscript:", 1)[0]
    metadata = json.loads(metadata_text)
    assert metadata == {"client": "generic"}
