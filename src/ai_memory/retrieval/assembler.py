from __future__ import annotations

from ai_memory.core.models import MemoryRecord


def assemble_context(records: list[MemoryRecord], title: str = "Retrieved Memory") -> str:
    if not records:
        return f"# {title}\n\n_No relevant memory found._"

    sections = [f"# {title}"]
    for record in records:
        sections.extend(
            [
                "",
                f"## {record.uri}",
                f"- Type: {record.type}",
                f"- Status: {record.status}",
                "- Memory:",
                f"  {record.content}",
            ]
        )
    return "\n".join(sections)


def hook_json(event: str, context: str) -> dict[str, dict[str, str]]:
    return {
        "hookSpecificOutput": {
            "hookEventName": event,
            "additionalContext": context,
        }
    }
