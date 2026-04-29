from ai_memory.core.models import MemoryCandidate
from ai_memory.core.policy import route_candidate
from ai_memory.core.uri import ParsedMemoryUri, parse_memory_uri


def test_parse_project_uri():
    parsed = parse_memory_uri("project://github.com/acme/app/testing")

    assert parsed == ParsedMemoryUri(
        namespace="project",
        authority="github.com",
        parts=("acme", "app", "testing"),
    )


def test_parse_system_uri():
    parsed = parse_memory_uri("system://boot")

    assert parsed == ParsedMemoryUri(namespace="system", authority="", parts=("boot",))


def test_reject_invalid_namespace():
    try:
        parse_memory_uri("unknown://github.com/acme/app/testing")
    except ValueError as exc:
        assert "Unsupported memory namespace" in str(exc)
    else:
        raise AssertionError("invalid namespace should fail")


def test_reject_query_string():
    try:
        parse_memory_uri("project://github.com/acme/app/testing?x=1")
    except ValueError as exc:
        assert "Memory URI must not include query or fragment" in str(exc)
    else:
        raise AssertionError("query string should fail")


def test_reject_fragment():
    try:
        parse_memory_uri("project://github.com/acme/app/testing#frag")
    except ValueError as exc:
        assert "Memory URI must not include query or fragment" in str(exc)
    else:
        raise AssertionError("fragment should fail")


def test_reject_missing_authority_for_non_system_namespace():
    try:
        parse_memory_uri("project:/acme/app/testing")
    except ValueError as exc:
        assert "Memory URI requires an authority" in str(exc)
    else:
        raise AssertionError("missing authority should fail")


def test_reject_missing_path():
    try:
        parse_memory_uri("project://github.com")
    except ValueError as exc:
        assert "Memory URI requires a path" in str(exc)
    else:
        raise AssertionError("missing path should fail")


def test_low_risk_command_auto_approves():
    candidate = MemoryCandidate(
        uri="project://github.com/acme/app/commands",
        type="project_command",
        scope="project",
        content="Use pnpm test for tests.",
        summary="Test command is pnpm test.",
        confidence=0.91,
        risk="low",
        evidence="package.json scripts were checked",
        tags=("testing",),
        triggers=("pnpm", "test"),
        repo_id="github.com/acme/app",
    )

    decision = route_candidate(candidate, auto_write_confidence=0.85)

    assert decision.action == "auto_write"
    assert decision.reason == "low-risk high-confidence candidate"


def test_testing_rule_requires_review_even_when_confident():
    candidate = MemoryCandidate(
        uri="project://github.com/acme/app/testing",
        type="testing_rule",
        scope="project",
        content="Use pnpm test for tests.",
        summary="Test command is pnpm test.",
        confidence=0.95,
        risk="low",
        evidence="user confirmed testing policy",
        tags=("testing",),
        triggers=("pnpm", "test"),
        repo_id="github.com/acme/app",
    )

    decision = route_candidate(candidate, auto_write_confidence=0.85)

    assert decision.action == "review"
    assert decision.reason == "high-impact memory type requires review"
