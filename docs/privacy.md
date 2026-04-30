# Privacy

`ai-memory` must not store secrets as durable memory.

## Redacted content

- Bearer tokens.
- API key assignments.
- Password assignments.
- Private key blocks.
- Database URL passwords.

## Sensitive paths

The first version treats these as sensitive:

- `.env` and `.env.*`
- `*.pem`
- `*.key`
- `id_rsa`
- `id_ed25519`
- `credentials.json`
- paths under `.ssh` or `.aws`

## Review policy

High-impact memory types such as user preferences, security constraints, testing rules, API contracts, and architecture decisions enter the review queue instead of being auto-written.
