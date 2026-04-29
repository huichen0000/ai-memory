# AI Memory Design

Date: 2026-04-29
Status: Draft for user review

## 1. Goal

Build a local-first, multi-tool, semi-automatic long-term memory system for AI coding tools.

The system should let multiple AI coding tools share one memory store, retrieve relevant context at session start or prompt time, capture useful learnings at session end, and import historical transcripts during initialization.

It is not a Claude-only memory layer, a pure vector database, a raw transcript archive, a Markdown-only note system, a team collaboration platform, or a first-version web dashboard.

## 2. Confirmed Decisions

| Decision | Choice |
|---|---|
| Architecture | Hybrid minimal |
| Interfaces | MCP plus CLI context/capture/import |
| Deployment | Personal local-first |
| Language | Python |
| Storage | SQLite plus JSONL review queue |
| First-class clients | Claude Code, Codex CLI, Gemini CLI, generic MCP client |
| Future clients | Cursor, Cline, Aider, Continue, OpenCode, Windsurf, Copilot, custom agents |
| Historical initialization | Auto-discover plus preview confirmation |
| Retrieval | Rule-based, keyword, triggers, optional embeddings |
| Extraction | Unified pluggable extractor provider |
| Write policy | Semi-automatic |
| Privacy | Basic redaction, sensitive source blacklist, user confirmation |
| Review | CLI plus `review-queue.jsonl` |
| Nocturne Memory relationship | Reference MCP, URI, versioning, boot, and trigger ideas, but do not depend on Nocturne |

## 3. Architecture

```text
AI coding tools
  Claude Code / Codex CLI / Gemini CLI / Cursor / Cline / Aider / ...
        │
        │ MCP / hooks / wrapper / importer
        ▼
ai-memory
        │
        ├─ CLI
        │   ├─ init
        │   ├─ discover
        │   ├─ import
        │   ├─ context
        │   ├─ capture
        │   ├─ review
        │   ├─ search
        │   └─ mcp serve
        │
        ├─ MCP Server
        │   ├─ memory_context
        │   ├─ memory_search
        │   ├─ memory_read
        │   ├─ memory_propose
        │   └─ memory_write
        │
        ├─ Adapter Layer
        │   ├─ claude-code
        │   ├─ codex-cli
        │   ├─ gemini-cli
        │   ├─ generic-mcp
        │   ├─ generic-cli
        │   └─ generic-transcript
        │
        ├─ Memory Core
        │   ├─ URI model
        │   ├─ scope
        │   ├─ versioning
        │   ├─ source/evidence
        │   └─ policy
        │
        ├─ Retrieval
        │   ├─ environment detection
        │   ├─ deterministic lookup
        │   ├─ SQLite FTS
        │   ├─ triggers
        │   ├─ optional embedding
        │   └─ context assembly
        │
        ├─ Extraction
        │   ├─ transcript normalization
        │   ├─ sanitization
        │   ├─ extractor provider
        │   ├─ validation
        │   ├─ dedupe
        │   └─ risk routing
        │
        └─ Store
            ├─ SQLite
            ├─ raw transcript archive
            └─ review-queue.jsonl
```

The core system is tool-agnostic. Tool-specific behavior lives only in adapters.

## 4. Memory Model

Each memory is a structured record, not a plain chat summary.

```json
{
  "id": "mem_...",
  "uri": "project://github.com/acme/app/testing",
  "type": "testing_rule",
  "scope": "project",
  "content": "This project uses pnpm test for tests.",
  "summary": "Test command is pnpm test.",
  "tags": ["testing", "pnpm"],
  "triggers": ["test", "pnpm", "ci"],
  "status": "approved",
  "confidence": 0.94,
  "risk": "low",
  "source": {
    "client": "claude-code",
    "session_id": "sess_...",
    "evidence": "User confirmed it and package.json was checked."
  },
  "environment": {
    "repo_id": "github.com/acme/app",
    "branch": null,
    "path_glob": null
  },
  "version": 1,
  "created_at": "...",
  "updated_at": "...",
  "expires_at": null
}
```

Required properties:

- `uri`: stable logical location.
- `type`: memory category.
- `scope`: global, org, project, branch, path, tool, or system.
- `content`: authoritative memory text.
- `source` and `evidence`: provenance for audit and rollback.
- `confidence` and `risk`: used by write policy.
- `status`: controls retrieval and review behavior.
- `version`: supports rollback.

## 5. URI Namespaces

First version supports:

```text
global://
org://
project://
branch://
path://
tool://
system://
```

Examples:

```text
global://user/preferences
global://user/workflow

project://github.com/acme/app/commands
project://github.com/acme/app/testing
project://github.com/acme/app/pitfalls
project://github.com/acme/app/decisions

branch://github.com/acme/app/feature-billing/state
branch://github.com/acme/app/feature-billing/todos

path://github.com/acme/app/apps-web
path://github.com/acme/app/legacy-payment

tool://claude-code/notes
tool://codex-cli/notes
tool://gemini-cli/notes

system://boot
system://recent
system://index
```

`system://boot` stores initialization protocol, not all memory content.

## 6. Memory Types

First-version built-in types:

```text
user_preference
workflow_rule
project_overview
project_command
coding_style
testing_rule
architecture_decision
api_contract
security_constraint
pitfall
bug_pattern
dependency_note
branch_state
task_todo
tool_note
external_reference
```

Memory type affects risk routing and retrieval.

## 7. Session Start Flow

```text
tool starts
  → ai-memory context
  → detect cwd/git/branch/language/framework
  → deterministic lookup:
      system/global/tool/project/branch/path
  → keyword/trigger search
  → optional semantic search
  → ranking
  → context assembly
  → inject short context
```

Example output:

```md
# Retrieved Memory

## Global Preferences
- User prefers Chinese responses.
- Keep code changes minimal; do not refactor unrelated code.

## Current Project
- This project uses pnpm.
- Test command is `pnpm test`.

## Relevant Pitfalls
- Stripe webhook signature verification must use raw body.
```

## 8. Retrieval and Ranking

Retrieval stages:

1. Environment detection.
2. Deterministic lookup for system, global, tool, project, branch, and path memory.
3. SQLite FTS keyword and trigger search.
4. Optional embedding search if configured.
5. Ranking and truncation.
6. Context assembly.

Ranking considers:

- Scope specificity.
- Status.
- Trigger or keyword match.
- Optional semantic similarity.
- Confidence.
- Recency.
- Risk and staleness penalties.

Default context budget:

```text
max_items: 12
max_chars: 6000
```

Do not inject rejected, expired, conflicted, sensitive, or low-confidence proposed memories by default.

## 9. Session End Capture Flow

```text
tool stops
  → ai-memory capture
  → find latest transcript
  → normalize transcript
  → archive raw transcript
  → sanitize secrets
  → call extractor provider
  → validate candidates
  → dedupe / conflict detection
  → route by risk
  → auto-write or review queue
```

Example output:

```text
Capture complete.

Candidates extracted: 8
Auto-approved: 3
Review queued: 4
Discarded: 1

Review with:
  ai-memory review
```

If extractor configuration is missing or fails, archive the transcript and report that extraction was skipped or failed. Do not fail silently.

## 10. Historical Initialization

Historical transcript import uses auto-discovery with preview confirmation.

```bash
ai-memory discover
```

Example output:

```text
Found transcript sources:

[1] Claude Code
    Sessions: 128
    Date range: 2025-12-10 → 2026-04-29
    Risk: medium

[2] Codex CLI
    Sessions: 34
    Date range: 2026-02-01 → 2026-04-29
    Risk: medium
```

Then import confirmed sources:

```bash
ai-memory import --source 1 --extract --review-only
```

Rules:

- Auto-discover, but do not auto-import.
- Preview and confirm before import.
- Bulk historical import is conservative by default.
- Old transcript memories receive a recency penalty.
- Raw transcripts are archived separately from durable memory.

## 11. Write Policy

The write policy is semi-automatic.

### Auto-write

Allowed when all are true:

```text
risk = low
confidence >= 0.85
no sensitive content
no conflict
type allows auto-write
```

Auto-write types:

```text
project_command
branch_state
task_todo
dependency_note
tool_note
low-risk pitfall
```

Status:

```text
auto_approved
```

### Review queue

Queue when memory is high-impact, uncertain, conflicting, or policy-sensitive.

Types queued by default:

```text
user_preference
workflow_rule
architecture_decision
api_contract
security_constraint
coding_style
testing_rule
```

Also queue:

- Medium or low confidence candidates.
- Conflicting memories.
- Candidates with uncertain scope.
- Memories that change user behavior or project policy.

Status:

```text
proposed
```

## 12. Review Queue

Review has two interfaces:

```text
CLI:
  ai-memory review
  ai-memory approve <id>
  ai-memory reject <id>
  ai-memory edit <id>

File:
  ~/.ai-memory/review-queue.jsonl
```

Review item format:

```json
{
  "id": "rev_...",
  "candidate": {},
  "reason": "testing_rule requires review",
  "source": {},
  "status": "pending",
  "created_at": "..."
}
```

Approving a review item writes it to SQLite and creates source and version records.

## 13. Privacy Policy

Default redaction covers:

```text
API key
Bearer token
cookie
password
private key
SSH key
.env values
cloud credentials
npm/pip tokens
database URL password
```

Sensitive sources require confirmation or are skipped by default:

```text
.env
.env.*
*.pem
*.key
id_rsa
id_ed25519
credentials.json
.aws/credentials
.ssh/*
browser cookie/session exports
password manager exports
```

Sensitive content is never written as durable memory. Raw transcript archives must be removable.

## 14. CLI Interface

Core commands:

```bash
ai-memory init
ai-memory discover
ai-memory import
ai-memory context
ai-memory capture
ai-memory review
ai-memory approve
ai-memory reject
ai-memory search
ai-memory read
ai-memory add
ai-memory mcp serve
ai-memory doctor
```

Wrapper commands:

```bash
aiwrap codex "fix failing tests"
aiwrap gemini "review this module"
aiwrap --client aider -- aider src/foo.py
```

## 15. MCP Interface

First-version MCP tools:

```text
memory_context
memory_search
memory_read
memory_propose
memory_write
memory_update
```

MCP write operations must respect the same policy as CLI write operations. High-impact writes are queued for review and cannot bypass policy.

## 16. Tool Support

| Tool | Strategy |
|---|---|
| Claude Code | MCP + hooks + import |
| Codex CLI | wrapper + import |
| Gemini CLI | wrapper + import + MCP if available |
| Generic MCP client | MCP |
| Generic CLI | wrapper |
| Generic transcript | import |

Future adapters:

```text
Cursor
Cline
Aider
Continue
OpenCode
Windsurf
Copilot
custom agents
```

Adapters are responsible only for discovery, transcript normalization, latest-session lookup, and installation hints. Extraction, retrieval, privacy, and write policy remain centralized.

## 17. Project Structure

```text
ai-memory/
  pyproject.toml
  README.md
  AGENTS.md

  src/
    ai_memory/
      cli/
      core/
      store/
      retrieval/
      extraction/
      adapters/
      mcp/
      wrappers/
      review/
      privacy/
      utils/

  tests/
    unit/
    integration/
    fixtures/
      transcripts/
        claude-code/
        codex-cli/
        gemini-cli/
        generic/

  docs/
    architecture.md
    memory-model.md
    adapter-guide.md
    privacy.md
```

## 18. First-Version Scope

Must include:

- `ai-memory init`.
- SQLite schema and migrations.
- URI validation.
- Environment detection.
- Context retrieval and assembly.
- SQLite FTS.
- Review queue CLI and JSONL storage.
- Generic transcript import.
- At least Claude Code adapter for latest session capture.
- Basic Codex and Gemini discovery/import hooks where feasible.
- MCP server with core tools.
- Privacy redaction and sensitive path checks.

Explicitly not included in first version:

- Web dashboard.
- Team accounts or permissions.
- Remote HTTP service.
- Multi-device sync.
- Required vector DB.
- Browser extension.
- Complex graph UI.
- Deep adapter support for every tool.

## 19. SQLite Schema Draft

Core tables:

```text
memories
memory_sources
memory_versions
sessions
review_items
memory_tags
memory_triggers
memory_fts
```

`memories` contains current canonical memory content and status.

`memory_versions` stores immutable history for rollback.

`memory_sources` stores provenance and evidence.

`sessions` stores normalized session metadata and transcript references.

`review_items` stores pending or completed review candidates.

`memory_fts` supports full-text search over URI, content, summary, tags, and triggers.

## 20. Configuration

Default path:

```text
~/.ai-memory/config.yaml
```

Example:

```yaml
store:
  type: sqlite
  path: ~/.ai-memory/memory.db

paths:
  raw_dir: ~/.ai-memory/raw
  log_dir: ~/.ai-memory/logs
  review_queue: ~/.ai-memory/review-queue.jsonl

extractor:
  provider: command
  command: null
  model: null
  api_key_env: null
  max_input_chars: 60000

embedding:
  enabled: false
  provider: null
  model: null
  api_key_env: null

retrieval:
  max_items: 12
  max_chars: 6000

policy:
  auto_write_confidence: 0.85
  review_high_impact_types: true

privacy:
  redact_secrets: true
  confirm_sensitive_sources: true

clients:
  claude-code:
    enabled: true
  codex-cli:
    enabled: true
  gemini-cli:
    enabled: true
```

If extractor is not configured, capture can archive transcripts but should not extract memories.

## 21. Error Handling

Rules:

- Do not fail silently.
- Transcript archive can succeed even if extraction fails.
- Context retrieval failures should degrade gracefully and not block tool startup for long.
- MCP writes must respect review policy.
- Invalid config, SQLite lock, parse failures, missing provider credentials, and sensitive source warnings must be explicit.

## 22. Testing Plan

Unit tests:

- URI parse and validation.
- Repo ID normalization.
- Secret redaction.
- Risk policy.
- Candidate validation.
- Ranking.
- Context assembly.
- Review queue read/write.
- SQLite CRUD.

Adapter tests:

- Discovery returns expected sources.
- Normalization returns unified transcript.
- Latest session lookup works.
- Bad transcript errors clearly.

Integration tests:

- Generic transcript import to archive to candidate to review queue.
- Low-risk `project_command` auto-writes and becomes searchable.
- High-impact `testing_rule` queues for review and can be approved.
- Context excludes rejected, proposed, conflicted, expired, and sensitive memories.
- MCP tools return expected results.

Privacy tests:

- API key redaction.
- Bearer token redaction.
- Private key redaction.
- Database URL password redaction.
- Sensitive path detection.

CLI smoke tests:

```bash
ai-memory init
ai-memory add ...
ai-memory search ...
ai-memory context ...
ai-memory review
ai-memory mcp serve --help
```

## 23. Acceptance Scenarios

1. Manual memory retrieval:
   - Add `project://local/demo/commands`.
   - Run `ai-memory context --prompt "run tests"`.
   - Context includes the test command.

2. Generic transcript import:
   - Run `ai-memory import --client generic --path ./chat.md --extract`.
   - Transcript is archived.
   - Candidates are extracted.
   - Low-risk candidates are auto-approved.
   - High-impact candidates are queued.

3. Review approval:
   - Run `ai-memory review`.
   - Approve an item.
   - Search finds the approved memory.

4. Claude hook JSON:
   - Run `ai-memory context --format hook-json --event SessionStart`.
   - Output is valid hook JSON with `additionalContext`.

5. MCP query:
   - MCP client calls `memory_context`, `memory_search`, and `memory_read`.
   - Tools return SQLite-backed memory.

6. Privacy:
   - Transcript with token-like values is imported.
   - Tokens are redacted or candidate is rejected.

## 24. Open Defaults

Use these defaults unless changed later:

```text
Project name: ai-memory
Python package: ai_memory
CLI command: ai-memory
Wrapper command: aiwrap
Extractor default: optional; unset means archive-only capture
```

## 25. Implementation Sequence Preview

Implementation should be planned separately. A reasonable sequence is:

1. Project skeleton and config.
2. Core models, URI parser, and policy.
3. SQLite store and migrations.
4. Review queue.
5. Privacy redaction.
6. Context retrieval.
7. Generic transcript import/capture.
8. Extractor provider interface.
9. MCP server.
10. Claude Code adapter and hook output.
11. Codex/Gemini wrapper/importer.
12. Tests and documentation.

Implementation must not start until this design is reviewed and approved.
