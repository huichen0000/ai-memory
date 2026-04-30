from __future__ import annotations

import argparse
import subprocess
from typing import Sequence


def build_wrapped_prompt(context: str, prompt: str) -> str:
    return f"{context.rstrip()}\n\n# User Request\n{prompt}"


def run(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aiwrap")
    parser.add_argument("client")
    parser.add_argument("prompt", nargs="?")
    args, remainder = parser.parse_known_args(argv)

    if args.prompt is None:
        parser.error("aiwrap requires a prompt for the first version")
    command = [args.client, build_wrapped_prompt("", args.prompt), *remainder]
    completed = subprocess.run(command, check=False)
    return completed.returncode


def main() -> None:
    raise SystemExit(run())
