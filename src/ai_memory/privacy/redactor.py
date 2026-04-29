from __future__ import annotations

import re

BEARER_RE = re.compile(r"Bearer\s+[^\s]+")
DATABASE_URL_RE = re.compile(r"(postgres(?:ql)?://[^:\s]+):([^@\s]+)@")
API_KEY_RE = re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)([^\s]+)")
PASSWORD_RE = re.compile(r"(?i)(password\s*[=:]\s*)([^\s]+)")
PRIVATE_KEY_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----")


def redact_secrets(text: str) -> str:
    redacted = BEARER_RE.sub("Bearer [REDACTED:BEARER_TOKEN]", text)
    redacted = DATABASE_URL_RE.sub(r"\1:[REDACTED]@", redacted)
    redacted = API_KEY_RE.sub(r"\1[REDACTED:API_KEY]", redacted)
    redacted = PASSWORD_RE.sub(r"\1[REDACTED:PASSWORD]", redacted)
    redacted = PRIVATE_KEY_RE.sub("[REDACTED:PRIVATE_KEY]", redacted)
    return redacted
