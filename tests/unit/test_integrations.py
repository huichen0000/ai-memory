from pathlib import Path

from ai_memory.cli.main import build_parser
from ai_memory.integrations.snippets import claude_code_hook_command


def test_claude_code_hook_command_is_parseable(tmp_path: Path):
    command = claude_code_hook_command(tmp_path / ".ai-memory", "UserPromptSubmit")

    args = build_parser().parse_args(command.split()[1:])

    assert args.command == "context"
    assert args.format == "hook-json"
    assert args.event == "UserPromptSubmit"
