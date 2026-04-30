# ai-memory

Local-first multi-tool memory for AI coding agents.

## First-version scope

- SQLite memory store.
- CLI commands for init, add, search, context, import, review, and MCP serving.
- JSONL review queue.
- Privacy redaction for common secrets.
- Generic transcript import.
- Initial Claude Code, Codex CLI, and Gemini CLI adapters.

## Install for development

```bash
python -m pip install -e ".[dev]"
```

## Initialize

```bash
ai-memory init
```

## Add and retrieve memory

```bash
ai-memory add project://local/demo/commands "Use pytest for tests."
ai-memory search pytest
ai-memory context --prompt "run tests"
```

## Import a generic transcript

```bash
ai-memory import --client generic --path ./chat.md --archive-only
```

## Review queue

```bash
ai-memory review
ai-memory approve rev_example
ai-memory reject rev_example
```

## MCP server

```bash
ai-memory mcp serve
```
