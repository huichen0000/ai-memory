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
ai-memory import --client generic --path ./chat.md --archive-only --redact-archive
```

Warning: `--archive-only` stores transcript text directly under `raw/generic` in the local memory home. Sensitive source paths are rejected by default and require `--allow-sensitive-source`, but allowed archive contents are still not redacted.

## Historical initialization

To initialize memory from previous AI-tool transcripts, run:

```bash
ai-memory history init --clients all --review-only --redact-archive
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

Privacy note: raw archives may contain the original transcript text. Sensitive source paths are rejected by default. `--allow-sensitive-source` only applies to explicit generic imports and `history init --include-generic`; sensitive paths discovered from built-in clients are always skipped. Use `--redact-archive` to redact common secrets (API keys, passwords, bearer tokens, private keys, database credentials) from archived content. Redaction and validation protect extracted durable memories, but raw archives without redaction are local copies of source transcripts.

## Review queue

```bash
ai-memory review
ai-memory approve rev_example
ai-memory reject rev_example
```

Approving a pending review item writes the candidate to SQLite as approved memory. If an approved or auto-approved memory already exists with the same URI and identical content, approval is treated as a duplicate and does not create a second memory. If the URI exists with different content, approval is blocked so the conflict can be reviewed explicitly.

## Current limitations

- Claude Code hooks are not installed automatically; generate or copy integration snippets manually.
- MCP writes are deliberately conservative: untrusted MCP writes are queued for review, server MCP writes are also review-only, and broad scopes (`global`, `system`, `org`, `tool`) cannot be auto-approved.
- Candidate writes require URI namespace and `scope` to match; this protects scoped retrieval but means malformed historical/external extractor output is discarded or queued instead of silently normalized.
- Retrieval is deterministic keyword, trigger, path, branch, repo, and scope ranking over SQLite FTS; optional embeddings are not implemented yet.
- The storage model is SQLite-first and does not implement Nocturne-style graph nodes, aliases, or path caches yet.

## Suggested roadmap

1. Add conflict-aware update commands: compatible updates can create new `memory_versions`, incompatible content can remain pending, and operators can explicitly merge/reject/replace.
2. Add optional semantic search after deterministic scope, trigger, path, and FTS retrieval are stable.
3. Strengthen Claude Code, Codex, and Gemini adapters with more complete transcript format parsing.
4. Add conflict-aware version merge commands for compatible memory updates.

## CLI commands

```bash
ai-memory init
ai-memory add
ai-memory search
ai-memory context
ai-memory discover
ai-memory review
ai-memory approve
ai-memory reject
ai-memory import
ai-memory history init
ai-memory capture
ai-memory wiki
ai-memory web
ai-memory server
ai-memory mcp serve
ai-memory system init
ai-memory memory show
ai-memory memory list
ai-memory memory update
```

## Combined server (with auth)

For multi-user deployments, use the combined server which includes MCP, web dashboard, and user authentication:

```bash
ai-memory server --port 8080
```

This starts a single server that serves:
- **Web dashboard** at `/`
- **MCP tools** at `/mcp` (with API key or JWT auth)
- **Auth APIs** at `/api/auth/*`

### Authentication

**Register a user:**
```bash
curl -X POST "http://localhost:8080/api/auth/register?username=alice&password=secret"
```

**Login:**
```bash
curl -X POST "http://localhost:8080/api/auth/login?username=alice&password=secret"
```

Returns: `{"token": "...", "user": {...}}`

**Use MCP with API key:**
```bash
# Set in Claude Code config
mcp__ai-memory__url=http://localhost:8080/mcp
mcp__ai-memory__api_key=your-api-key-here
```

### User management (admin only)

```bash
# List users
curl -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/admin/users

# Create user
curl -X POST "http://localhost:8080/api/admin/users?username=bob&password=secret&role=write" \
  -H "Authorization: Bearer $TOKEN"

# Delete user
curl -X DELETE "http://localhost:8080/api/admin/users/$USER_ID" \
  -H "Authorization: Bearer $TOKEN"
```

## MCP server (local)

```bash
ai-memory mcp serve
```
