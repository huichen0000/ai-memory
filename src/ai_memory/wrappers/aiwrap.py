from __future__ import annotations

import argparse
import subprocess
import sys
from typing import Sequence


def build_wrapped_prompt(context: str, prompt: str) -> str:
    return f"{context.rstrip()}\n\n# User Request\n{prompt}"


def run(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aiwrap")
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        parser.error("aiwrap requires: aiwrap <client> [client args...] -- <prompt>")
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
    command = [client, *client_args, build_wrapped_prompt("", prompt)]
    completed = subprocess.run(command, check=False)
    return completed.returncode


def main() -> None:
    raise SystemExit(run())
