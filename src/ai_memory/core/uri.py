from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

SUPPORTED_NAMESPACES = {"global", "org", "project", "branch", "path", "tool", "system"}


@dataclass(frozen=True)
class ParsedMemoryUri:
    namespace: str
    authority: str
    parts: tuple[str, ...]


def parse_memory_uri(uri: str) -> ParsedMemoryUri:
    parsed = urlparse(uri)
    if parsed.scheme not in SUPPORTED_NAMESPACES:
        raise ValueError(f"Unsupported memory namespace: {parsed.scheme}")
    if not parsed.netloc and parsed.scheme != "system":
        raise ValueError(f"Memory URI requires an authority: {uri}")
    path_parts = tuple(part for part in parsed.path.split("/") if part)
    if parsed.scheme == "system" and parsed.netloc:
        path_parts = (parsed.netloc, *path_parts)
        authority = ""
    else:
        authority = parsed.netloc
    if not path_parts:
        raise ValueError(f"Memory URI requires a path: {uri}")
    return ParsedMemoryUri(namespace=parsed.scheme, authority=authority, parts=path_parts)


def validate_memory_uri(uri: str) -> None:
    parse_memory_uri(uri)
