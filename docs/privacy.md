# Privacy

`ai-memory` should not store secrets as durable memory. In the first version, secret redaction and candidate validation apply during adapter normalization and candidate routing, not to every local archive operation.

## Redacted content

- Bearer tokens.
- API key assignments.
- Password assignments.
- Private key blocks.
- Database URL passwords.

## Sensitive paths

The first version includes a utility that treats these as sensitive:

- `.env` and `.env.*`
- `*.pem`
- `*.key`
- `id_rsa`
- `id_ed25519`
- `credentials.json`
- paths under `.ssh` or `.aws`

This sensitive-path detection is not enforced by `ai-memory import --archive-only` yet.

## Raw archive-only import

`ai-memory import --client generic --path <file> --archive-only` copies transcript text directly into `raw/generic` under the local memory home. It does not redact the transcript and does not screen the source path for sensitive filenames in this first version. Only use archive-only import with transcripts that are already safe to store locally.

## Review policy

High-impact memory types such as user preferences, security constraints, testing rules, API contracts, and architecture decisions enter the review queue instead of being auto-written.
