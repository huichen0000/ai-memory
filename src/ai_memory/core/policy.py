from __future__ import annotations

from ai_memory.core.models import MemoryCandidate, RouteDecision

AUTO_WRITE_TYPES = {
    "project_command",
    "branch_state",
    "task_todo",
    "dependency_note",
    "tool_note",
    "pitfall",
}

HIGH_IMPACT_TYPES = {
    "user_preference",
    "workflow_rule",
    "architecture_decision",
    "api_contract",
    "security_constraint",
    "coding_style",
    "testing_rule",
}

BROAD_SCOPES = {"global", "system", "org", "tool"}


def route_candidate(candidate: MemoryCandidate, auto_write_confidence: float) -> RouteDecision:
    if candidate.confidence < 0.5:
        return RouteDecision(action="discard", reason="candidate confidence is too low")
    if candidate.scope in BROAD_SCOPES:
        return RouteDecision(action="review", reason="broad-scope memory requires review")
    if candidate.type in HIGH_IMPACT_TYPES:
        return RouteDecision(action="review", reason="high-impact memory type requires review")
    if candidate.risk != "low":
        return RouteDecision(action="review", reason="non-low risk candidate requires review")
    if candidate.confidence < auto_write_confidence:
        return RouteDecision(action="review", reason="candidate confidence is below auto-write threshold")
    if candidate.type not in AUTO_WRITE_TYPES:
        return RouteDecision(action="review", reason="memory type is not auto-writeable")
    return RouteDecision(action="auto_write", reason="low-risk high-confidence candidate")
