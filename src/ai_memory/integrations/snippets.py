from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


SUPPORTED_CLIENTS = ("claude-code", "codex-cli", "gemini-cli")


@dataclass(frozen=True)
class IntegrationStatus:
    client: str
    status: str
    detail: str


def claude_code_hook_command(home: Path, event: str) -> str:
    return f'ai-memory context --home "{home}" --format hook-json --event {event}'


def _claude_command_hook(home: Path, event: str) -> dict[str, object]:
    return {
        "type": "command",
        "command": claude_code_hook_command(home, event),
        "timeout": 10,
        "statusMessage": "Loading ai-memory context...",
    }


def claude_code_settings_snippet(home: Path) -> dict[str, object]:
    return {
        "hooks": {
            "SessionStart": [
                {
                    "hooks": [_claude_command_hook(home, "SessionStart")]
                }
            ],
            "UserPromptSubmit": [
                {
                    "hooks": [_claude_command_hook(home, "UserPromptSubmit")]
                }
            ],
        }
    }


def claude_code_snippet_text(home: Path) -> str:
    snippet = json.dumps(claude_code_settings_snippet(home), indent=2, ensure_ascii=False)
    return (
        "Claude Code integration is ccswitch-safe by default: no settings file was modified.\n"
        "Add this snippet to the active Claude Code profile/settings that ccswitch manages, "
        "or paste it through Claude Code's /hooks UI.\n\n"
        f"{snippet}"
    )


def wrapper_guidance(client: str, home: Path) -> str:
    executable = "codex" if client == "codex-cli" else "gemini"
    return (
        f"Use aiwrap to inject approved ai-memory context before launching {executable}.\n\n"
        f"Example:\n"
        f"  aiwrap {executable} -- \"your prompt here\"\n\n"
        f"ai-memory home: {home}\n"
        "For fully transparent use, point your shell alias or launcher at aiwrap instead of the raw client."
    )


def integration_status(client: str, home: Path) -> IntegrationStatus:
    if client == "claude-code":
        return IntegrationStatus(
            client=client,
            status="manual-snippet",
            detail="ccswitch-safe mode: generate a hook snippet instead of editing settings.json directly.",
        )
    if client in {"codex-cli", "gemini-cli"}:
        return IntegrationStatus(
            client=client,
            status="wrapper-available",
            detail=f"Use aiwrap with ai-memory home {home}.",
        )
    raise ValueError(f"Unsupported integration client: {client}")


def install_instructions(client: str, home: Path) -> str:
    if client == "claude-code":
        return claude_code_snippet_text(home)
    if client in {"codex-cli", "gemini-cli"}:
        return wrapper_guidance(client, home)
    raise ValueError(f"Unsupported integration client: {client}")
