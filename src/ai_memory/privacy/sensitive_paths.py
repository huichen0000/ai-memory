from __future__ import annotations

from pathlib import Path

SENSITIVE_NAMES = {
    ".env",
    "id_rsa",
    "id_ed25519",
    "credentials.json",
    "application_default_credentials.json",
}

SENSITIVE_SUFFIXES = {".pem", ".key"}
SENSITIVE_PARTS = {".ssh", ".aws"}


def is_sensitive_path(path: Path) -> bool:
    name = path.name
    if name in SENSITIVE_NAMES:
        return True
    if name.startswith(".env."):
        return True
    if path.suffix in SENSITIVE_SUFFIXES:
        return True
    return any(part in SENSITIVE_PARTS for part in path.parts)
