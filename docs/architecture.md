# Architecture

`ai-memory` is organized around a tool-agnostic core. Tool-specific behavior lives in adapters.

## Layers

- `core`: models, URI parsing, config, and write policy.
- `store`: SQLite persistence and FTS.
- `retrieval`: environment detection, ranking, and context assembly.
- `extraction`: transcript normalization, candidate validation, provider interface, and routing.
- `privacy`: redaction and sensitive path detection.
- `review`: JSONL review queue.
- `cli`: user commands.
- `mcp`: MCP tools and server.
- `adapters`: Claude Code, Codex CLI, Gemini CLI, and generic transcript discovery.

## Data flow

For session-start integration, a client hook can call `ai-memory context`, which searches approved memory and emits markdown or hook JSON. The first version exposes this command output but does not install client hooks automatically.

Transcript ingestion currently uses `ai-memory import --archive-only`, which archives transcript content for later processing. Archive-only import stores raw transcript text and does not redact secrets or screen sensitive paths before writing to `raw/generic`; a future `capture`-style flow can route extracted candidates through the write policy when that command surface exists.
