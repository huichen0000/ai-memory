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

Warning: `--archive-only` stores the transcript text directly under `raw/generic` in the local memory home. It does not redact secrets or screen sensitive paths in this first version, so only import transcripts that are safe for local archival.

## Historical initialization

To initialize memory from previous AI-tool transcripts, run:

```bash
ai-memory history init --clients all --review-only
```

This scans supported local clients (`claude-code`, `codex-cli`, and `gemini-cli`), archives discovered transcripts under `~/.ai-memory/raw/<client>/`, and extracts candidate memories when an extractor provider is configured.

The default is review-only: valid candidates are queued for review instead of being written directly to durable memory.

```bash
ai-memory review
ai-memory approve <review_id>
ai-memory reject <review_id>
```

Preview without writing anything:

```bash
ai-memory history init --clients all --dry-run
```

Allow low-risk, high-confidence candidates to be written automatically while high-impact candidates still go to review:

```bash
ai-memory history init --clients all --auto-write-low-risk
```

Include generic transcript files or directories:

```bash
ai-memory history init --include-generic ./old-chats --review-only
```

Privacy note: raw archives may contain the original transcript text. Redaction and validation protect extracted durable memories, but raw archives are local copies of source transcripts.

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
