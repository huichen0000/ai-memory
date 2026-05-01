# Privacy

`ai-memory` should not store secrets as durable memory. In the first version, secret redaction and candidate validation apply during adapter normalization and candidate routing, not to every local archive operation.

## Redacted content

- Bearer tokens.
- API key assignments.
- Password assignments.
- Private key blocks.
- Database URL passwords.

## Sensitive paths

The first version includes a utility that treats common secret-bearing filenames, suffixes, keywords, and credential directories as sensitive, including:

- `.env` and `.env.*`
- `*.pem` and `*.key`
- SSH private key names such as `id_rsa`, `id_ed25519`, `id_ecdsa`, and `id_dsa`
- credential names such as `credentials.json`, `client_secret.json`, `token.json`, and `secrets.json`
- names containing `secret`, `credential`, `token`, `private_key`, `private-key`, `service-account`, or `service_account`
- paths under credential directories such as `.ssh`, `.aws`, `.kube`, `.docker`, `.azure`, `.terraform.d`, `.cargo`, `.gradle`, `gcloud`, `gh`, or `hub`

Archive commands reject sensitive source paths by default after checking both the submitted path and resolved symlink target. `--allow-sensitive-source` only applies to explicit generic imports and `history init --include-generic`; sensitive paths discovered from built-in clients are always skipped.

## Raw archive-only import

`ai-memory import --client generic --path <file> --archive-only` copies transcript text directly into `raw/generic` under the local memory home. It rejects sensitive source paths by default and requires `--allow-sensitive-source` to archive them explicitly. Allowed archive contents are still raw local copies and are not redacted, so only use archive-only import with transcripts that are safe to store locally.

## Review policy

High-impact memory types such as user preferences, security constraints, testing rules, API contracts, and architecture decisions enter the review queue instead of being auto-written.
