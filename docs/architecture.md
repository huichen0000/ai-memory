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

Session start calls `ai-memory context`, which searches approved memory and emits markdown or hook JSON.

Transcript ingestion currently uses `ai-memory import`, which archives transcript content for later processing. A future `capture`-style flow can route extracted candidates through the write policy when that command surface exists.
