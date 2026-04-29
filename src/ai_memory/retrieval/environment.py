from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from urllib.parse import urlparse


GIT_TIMEOUT_SECONDS = 2


def _run_git(args: list[str], cwd: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    output = result.stdout.strip()
    return output or None


def _repo_id_from_remote(remote: str) -> str:
    if remote.startswith("git@") and ":" in remote:
        _, remainder = remote.split("@", 1)
        host, path = remainder.split(":", 1)
        normalized = f"{host}/{path}"
    elif "://" in remote:
        parsed = urlparse(remote)
        normalized = f"{parsed.netloc}{parsed.path}"
    else:
        normalized = remote.replace("\\", "/")
    normalized = normalized.strip().rstrip("/")
    if normalized.endswith(".git"):
        normalized = normalized[:-4]
    return normalized.lstrip("/")


def _local_repo_id(cwd: Path) -> str:
    resolved = cwd.resolve()
    digest = hashlib.sha1(str(resolved).encode("utf-8")).hexdigest()[:12]
    return f"local/{digest}"


def detect_environment(cwd: Path, client: str, prompt: str) -> dict[str, str | None]:
    resolved_cwd = cwd.resolve()
    git_root = _run_git(["rev-parse", "--show-toplevel"], resolved_cwd)
    branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], resolved_cwd)
    remote = _run_git(["remote", "get-url", "origin"], resolved_cwd)
    repo_id = _repo_id_from_remote(remote) if remote else _local_repo_id(resolved_cwd)
    return {
        "cwd": str(resolved_cwd),
        "client": client,
        "prompt": prompt,
        "git_root": git_root,
        "branch": branch,
        "remote": remote,
        "repo_id": repo_id,
    }
