from __future__ import annotations

from io import TextIOWrapper
from pathlib import Path
import sys
from typing import Any

import anyio
from ai_memory.retrieval.environment import detect_environment

from mcp.server.fastmcp import FastMCP
from mcp.server.stdio import stdio_server

from ai_memory.mcp.tools import memory_context, memory_read, memory_search, memory_write
from ai_memory.review.queue import ReviewQueue
from ai_memory.store.sqlite import SQLiteMemoryStore


def build_server(home: Path | None = None) -> FastMCP:
    memory_home = home or Path.home() / ".ai-memory"
    store = SQLiteMemoryStore(memory_home / "memory.db")
    store.initialize()
    queue = ReviewQueue(memory_home / "review-queue.jsonl")
    server = FastMCP("ai-memory")
    workspace = Path.cwd().resolve()

    def trusted_environment(prompt: str) -> dict[str, str | None]:
        return detect_environment(workspace, client="mcp", prompt=prompt)

    @server.tool()
    def memory_search_tool(
        query: str,
        limit: int = 10,
    ) -> dict[str, Any]:
        return memory_search(store, query, limit, trusted_environment(query))

    @server.tool()
    def memory_context_tool(
        prompt: str,
        max_items: int = 12,
    ) -> dict[str, Any]:
        return memory_context(store, prompt, max_items, trusted_environment(prompt))

    @server.tool()
    def memory_read_tool(
        memory_id: str,
    ) -> dict[str, Any]:
        return memory_read(
            store,
            memory_id,
            trusted_environment("memory read"),
        )

    @server.tool()
    def memory_write_tool(payload: dict[str, Any]) -> dict[str, Any]:
        return memory_write(store, queue, payload, trusted_environment("memory write"), review_only=True)

    return server


class _NonBlankAsyncTextReader:
    def __init__(self, wrapped: anyio.AsyncFile[str]) -> None:
        self._wrapped = wrapped

    def __aiter__(self) -> "_NonBlankAsyncTextReader":
        return self

    async def __anext__(self) -> str:
        while True:
            line = await self._wrapped.readline()
            if line == "":
                raise StopAsyncIteration
            if line.strip():
                return line


async def _run_stdio_async(home: Path | None = None) -> None:
    stdin = anyio.wrap_file(TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace"))
    stdout = anyio.wrap_file(TextIOWrapper(sys.stdout.buffer, encoding="utf-8"))
    async with stdio_server(stdin=_NonBlankAsyncTextReader(stdin), stdout=stdout) as (read_stream, write_stream):
        mcp = build_server(home)
        await mcp._mcp_server.run(  # noqa: SLF001
            read_stream,
            write_stream,
            mcp._mcp_server.create_initialization_options(),  # noqa: SLF001
        )


def main() -> None:
    anyio.run(_run_stdio_async)
