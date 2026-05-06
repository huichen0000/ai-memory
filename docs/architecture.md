# Architecture

`ai-memory` is organized around a tool-agnostic core. Tool-specific behavior lives in adapters.

## Layers

- `core`: models, URI parsing, config, and write policy.
- `store`: SQLite persistence and FTS.
- `retrieval`: environment detection, ranking, and context assembly.
- `extraction`: transcript normalization, candidate validation, provider interface, and routing.
- `privacy`: redaction and sensitive path detection.
- `review`: JSONL review queue.
- `cli`: user commands including `capture`, `wiki`, `system`, and `memory`.
- `mcp`: MCP tools and server (local stdio or remote HTTP).
- `adapters`: Claude Code, Codex CLI, Gemini CLI, and generic transcript discovery.
- `web`: local-only web dashboard UI (served by `ai-memory web`).
- `server`: combined MCP + web server with unified auth (served by `ai-memory server`).
- `auth`: user accounts, API keys, JWT tokens, and bcrypt password hashing.

## Data flow

For transparent integration, client hooks or wrappers call `ai-memory context`, which searches approved memory and emits markdown or hook JSON. `ai-memory integrate install claude-code` prints ccswitch-safe Claude Code hook snippets without editing `settings.json`; Codex CLI and Gemini CLI can use `aiwrap` to prepend approved memory context before launching the underlying client.

Transcript ingestion uses `ai-memory import --archive-only` for raw archival, or `ai-memory capture` for full pipeline: find latest transcript, normalize, archive, extract candidates, and route through write policy. Sensitive source paths are rejected by default after checking both submitted paths and resolved symlink targets.

Memory export uses `ai-memory wiki` to render a read-only Markdown projection of approved SQLite memories. SQLite remains the canonical store; wiki is a human/diff/LLM-friendly projection layer.
