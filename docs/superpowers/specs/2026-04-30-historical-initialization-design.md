# Historical Initialization Design

Date: 2026-04-30
Status: Approved for implementation planning

## 1. Goal

Add a safe one-command historical initialization flow that can discover past AI coding transcripts from supported tools, archive them locally, extract candidate memories, and route those candidates through the existing review policy.

The feature should make initial setup practical for users who have already used Claude Code, Codex CLI, Gemini CLI, or generic transcript files before installing `ai-memory`.

## 2. Non-Goals

This feature will not:

- Build a web dashboard.
- Add remote sync or cloud import.
- Automatically install hooks for any AI tool.
- Require embeddings or a vector database.
- Bypass the existing validation, redaction, and review policy.
- Guarantee perfect transcript parsing for every possible version of every client.
- Delete or mutate source transcript files from the original tools.

## 3. User-Facing CLI

Add a grouped historical initialization command:

```bash
ai-memory history init
```

Default behavior is intentionally conservative and equivalent to:

```bash
ai-memory history init --clients all --review-only
```

Supported options:

```bash
ai-memory history init --clients all
ai-memory history init --clients claude-code,codex-cli,gemini-cli
ai-memory history init --review-only
ai-memory history init --auto-write-low-risk
ai-memory history init --limit 100
ai-memory history init --dry-run
ai-memory history init --include-generic PATH
```

Option semantics:

- `--clients all`: scan all built-in tool adapters that support discovery.
- `--clients <list>`: comma-separated subset of `claude-code`, `codex-cli`, and `gemini-cli`.
- `--review-only`: queue all valid extracted candidates for review, even if policy would normally auto-write them.
- `--auto-write-low-risk`: allow the existing policy to auto-write low-risk, high-confidence candidates and queue high-impact candidates.
- `--limit N`: process at most N discovered transcript sources across selected clients after discovery sorting.
- `--dry-run`: discover and report what would happen without writing raw archives, review items, or SQLite memories.
- `--include-generic PATH`: include one generic transcript file or a directory of generic transcript files in addition to selected clients.

`--review-only` and `--auto-write-low-risk` are mutually exclusive. If neither is provided, use `--review-only`.

## 4. Default Safety Policy

Historical imports are higher risk than fresh session capture because old conversations may contain outdated instructions, temporary mistakes, or private data. Therefore the default path is:

1. Discover sources.
2. Archive transcripts locally.
3. Normalize and redact text before extraction.
4. Extract candidates only if an extractor provider is configured.
5. Validate candidates.
6. Put every valid candidate into the review queue.
7. Discard sensitive or invalid candidates.

The command must not directly approve durable memories unless the user explicitly passes `--auto-write-low-risk`.

Raw transcript archives may still contain original content. The command output must state this clearly whenever it writes archives.

## 5. Data Flow

```text
ai-memory history init
  -> parse options
  -> resolve selected clients
  -> discover sources through adapters
  -> include generic paths when provided
  -> sort and limit sources
  -> for each source:
       -> skip duplicate archive targets
       -> read transcript safely
       -> archive raw transcript unless dry-run
       -> normalize transcript through adapter
       -> redact normalized message text
       -> run extractor provider if configured
       -> validate candidates
       -> route candidates
       -> force review queue when review-only is active
       -> optionally auto-write low-risk candidates when requested
  -> print summary and next commands
```

The original transcript files are read-only inputs. The feature writes only under the configured ai-memory home directory.

## 6. New Module Boundary

Create a focused historical initialization module:

```text
src/ai_memory/history/
  __init__.py
  initializer.py
```

`initializer.py` owns orchestration only. It should reuse existing components instead of duplicating policy logic:

- adapters for discovery and normalization;
- `ReviewQueue` for queued memories;
- `SQLiteMemoryStore` for optional low-risk auto-write;
- `CommandExtractorProvider` through the existing extractor provider interface;
- candidate validation and routing from `ai_memory.extraction`;
- privacy redaction from `ai_memory.privacy`.

The CLI should stay thin: parse arguments, construct config, call initializer, print summary, and return an exit code.

## 7. Core Data Structures

Add lightweight dataclasses in `history.initializer`:

```python
@dataclass(frozen=True)
class HistorySource:
    client: str
    path: Path

@dataclass(frozen=True)
class HistoryInitOptions:
    clients: tuple[str, ...]
    include_generic: tuple[Path, ...]
    review_only: bool
    auto_write_low_risk: bool
    limit: int | None
    dry_run: bool

@dataclass(frozen=True)
class HistoryInitSummary:
    clients_scanned: int
    sources_found: int
    sources_processed: int
    transcripts_archived: int
    transcripts_skipped: int
    extraction_skipped: int
    candidates_extracted: int
    review_queued: int
    auto_written: int
    discarded: int
    errors: tuple[str, ...]
```

These structures keep CLI output and tests deterministic.

## 8. Discovery Rules

Built-in discovery should use the existing adapters:

- `ClaudeCodeAdapter.discover()` for Claude Code JSONL sessions.
- `CodexCliAdapter.discover()` for Codex CLI transcript-like files.
- `GeminiCliAdapter.discover()` for Gemini CLI transcript-like files.
- `GenericTranscriptAdapter` for `--include-generic` files.

Discovery failures for one client must not stop other clients. The summary should include a sanitized error string such as:

```text
claude-code: discovery failed: <message>
```

For directories passed through `--include-generic`, recursively include transcript-like files with suffixes:

```text
.md, .txt, .json, .jsonl
```

Hidden files and directories should be skipped.

## 9. Archive Rules

Archive raw transcripts under the configured home:

```text
~/.ai-memory/raw/<client>/<source-filename>
```

If the filename already exists, avoid overwrite by appending a short stable suffix derived from the source path, for example:

```text
session.jsonl
session-7f3a2c1b.jsonl
```

This differs from the existing single-file generic import command, which rejects duplicates. Historical initialization should continue processing other sources and avoid data loss.

In `--dry-run`, no archive directories or files are created.

## 10. Extraction Behavior

If no extractor provider is configured, the command should still discover and archive transcripts, then report:

```text
Extraction skipped: no extractor provider configured.
```

If a command extractor is configured, each normalized transcript is converted into extractor input text and sent to the provider. Extractor output must be validated through the existing candidate validation path.

A malformed extractor response for one transcript should increment `errors` and continue with the next transcript.

## 11. Routing Behavior

For each valid candidate:

- If `--review-only` is active, enqueue the candidate in `review-queue.jsonl` regardless of whether the normal policy would auto-write it.
- If `--auto-write-low-risk` is active, use the existing policy decision:
  - `auto_write`: write to SQLite as `auto_approved`;
  - `review`: enqueue to review queue;
  - `discard`: count as discarded.
- Sensitive or invalid candidates are discarded and must not be written to SQLite or the review queue.

Review queue entries should include a reason that indicates historical origin, for example:

```text
historical import from claude-code requires review
```

SQLite writes should include a change reason such as:

```text
historical import auto-write from claude-code
```

## 12. Error Handling

The command should be resilient:

- One bad transcript does not fail the whole run.
- One unavailable client does not fail other clients.
- Non-UTF-8 files are skipped and counted as errors.
- Malformed JSONL lines should be handled by the adapter where supported.
- Missing transcript directories are not fatal; they produce zero discovered sources.
- Invalid client names are user errors and return exit code 2.
- Invalid option combinations return exit code 2.

Exit codes:

- `0`: command completed, even if some sources were skipped with recoverable errors.
- `2`: invalid CLI usage or invalid options.
- `1`: unexpected initializer-level failure that prevented any meaningful processing.

## 13. Output Format

Human output should be concise but actionable:

```text
Historical initialization complete.

Clients scanned: 3
Sources found: 42
Sources processed: 42
Transcripts archived: 42
Extraction skipped: 0
Candidates extracted: 18
Review queued: 18
Auto-written: 0
Discarded: 2
Errors: 1

Raw transcripts were archived under: ~/.ai-memory/raw
Raw archives may contain original private content.
Review candidates with: ai-memory review
```

For `--dry-run`, output should say:

```text
Dry run only. No archives, review items, or memories were written.
```

## 14. Testing Plan

Unit tests should cover:

1. Client list parsing:
   - `all` resolves to built-in clients.
   - comma-separated subsets are accepted.
   - unknown clients return a CLI error.

2. Dry run:
   - discovers sources;
   - does not create archive files;
   - does not write review queue items;
   - does not write SQLite memories.

3. Review-only routing:
   - low-risk candidates are queued, not auto-written.
   - high-impact candidates are queued.

4. Auto-write routing:
   - low-risk high-confidence candidates become `auto_approved` memories.
   - high-impact candidates enter review queue.

5. Extractor missing:
   - transcripts can still be archived;
   - extraction skipped count increases;
   - output reports extraction skipped.

6. Per-source resilience:
   - one unreadable or malformed source records an error;
   - later valid sources still process.

7. Generic include:
   - file input is included;
   - directory input includes transcript-like files;
   - hidden files are skipped.

8. Archive naming:
   - duplicate basenames do not overwrite each other;
   - stable suffixes are deterministic.

## 15. Documentation Updates

Update `README.md` and `README_CN.md` with:

- how to run historical initialization;
- the default review-only behavior;
- the difference between raw archives and durable memories;
- how to configure an extractor provider;
- how to review imported candidates.

The documentation must not imply that historical initialization is fully risk-free. It should clearly state that raw archives may contain original transcript content.

## 16. Acceptance Criteria

The feature is complete when:

1. `ai-memory history init --dry-run` scans supported clients and writes nothing.
2. `ai-memory history init --clients all --review-only` archives discovered transcripts and queues extracted candidates when an extractor is configured.
3. `ai-memory history init --auto-write-low-risk` writes only low-risk high-confidence candidates directly and queues high-impact candidates.
4. Missing extractor configuration is reported explicitly and does not silently skip extraction.
5. A bad transcript does not stop the whole import.
6. Unit tests cover dry-run, review-only, auto-write, missing extractor, duplicate archive names, and generic include behavior.
7. Documentation explains privacy limits and review workflow in English and Chinese.
