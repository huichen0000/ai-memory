from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from ai_memory.core.config import init_home


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-memory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize local ai-memory storage")
    init_parser.add_argument("--home", type=Path, default=Path.home() / ".ai-memory")

    return parser


def run(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        config = init_home(args.home)
        print(f"Initialized ai-memory at {config.home}")
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


def main() -> None:
    raise SystemExit(run())
