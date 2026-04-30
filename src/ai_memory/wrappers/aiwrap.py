from __future__ import annotations

import argparse
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from ai_memory.core.config import load_config
from ai_memory.retrieval.assembler import assemble_context
from ai_memory.retrieval.ranking import rank_records
from ai_memory.store.sqlite import SQLiteMemoryStore


def build_wrapped_prompt(context: str, prompt: str) -> str:
    return f"{context.rstrip()}\n\n# User Request\n{prompt}"


def _tokenize(value: str) -> tuple[str, ...]:
    seen: list[str] = []
    for token in re.findall(r"[a-z0-9_-]+", value.lower()):
        if token not in seen:
            seen.append(token)
    return tuple(seen)


def _memory_context(home: Path, prompt: str) -> str:
    config = load_config(home)
    store = SQLiteMemoryStore(config.store_path)
    store.initialize()
    records = []
    seen: set[str] = set()
    for token in _tokenize(prompt):
        try:
            matches = store.search(token, limit=config.retrieval_max_items)
        except sqlite3.OperationalError:
            continue
        for record in matches:
            if record.id not in seen:
                seen.add(record.id)
                records.append(record)
    ranked = rank_records(records)[: config.retrieval_max_items]
    return assemble_context(ranked)


def run(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aiwrap")
    parser.add_argument("--home", type=Path, default=Path.home() / ".ai-memory")
    namespace, args = parser.parse_known_args(list(sys.argv[1:] if argv is None else argv))
    if not args:
        parser.error("aiwrap requires: aiwrap [--home PATH] <client> [client args...] -- <prompt>")
    client = args[0]
    rest = args[1:]
    if "--" not in rest:
        parser.error("aiwrap requires: aiwrap <client> [client args...] -- <prompt>")
    separator_index = rest.index("--")
    client_args = rest[:separator_index]
    prompt_parts = rest[separator_index + 1 :]
    if not prompt_parts:
        parser.error("aiwrap requires: aiwrap <client> [client args...] -- <prompt>")
    prompt = " ".join(prompt_parts)
    context = _memory_context(namespace.home, prompt)
    command = [client, *client_args, build_wrapped_prompt(context, prompt)]
    completed = subprocess.run(command, check=False)
    return completed.returncode


def main() -> None:
    raise SystemExit(run())
