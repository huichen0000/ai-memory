from __future__ import annotations

from pathlib import Path

SENSITIVE_NAMES = {
    ".env",
    ".netrc",
    ".npmrc",
    ".pypirc",
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
    "id_dsa",
    "credentials.json",
    "credentials.txt",
    "credentials.yaml",
    "credentials.yml",
    "application_default_credentials.json",
    "client_secret.json",
    "token.json",
    "secrets.json",
}

SENSITIVE_SUFFIXES = {".pem", ".key"}
SENSITIVE_PARTS = {
    ".ssh",
    ".aws",
    ".kube",
    ".gnupg",
    ".docker",
    ".azure",
    ".terraform.d",
    ".cargo",
    ".gradle",
    "gcloud",
    "gh",
    "hub",
}
SENSITIVE_KEYWORDS = ("secret", "credential", "token", "private_key", "private-key", "service-account", "service_account")


def is_sensitive_path(path: Path) -> bool:
    name = path.name.lower()
    if name in SENSITIVE_NAMES:
        return True
    if name.startswith(".env."):
        return True
    if path.suffix.lower() in SENSITIVE_SUFFIXES:
        return True
    if any(keyword in name for keyword in SENSITIVE_KEYWORDS):
        return True
    return any(part.lower() in SENSITIVE_PARTS for part in path.parts)
