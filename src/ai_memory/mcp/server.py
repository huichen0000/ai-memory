from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from ai_memory.mcp.tools import memory_context, memory_read, memory_search, memory_write
from ai_memory.review.queue import ReviewQueue
from ai_memory.store.sqlite import SQLiteMemoryStore


def build_server(home: Path | None = None) -> FastMCP:
    memory_home = home or Path.home() / ".ai-memory"
    store = SQLiteMemoryStore(memory_home / "memory.db")
    store.initialize()
    queue = ReviewQueue(memory_home / "review-queue.jsonl")
    server = FastMCP("ai-memory")

    @server.tool()
    def memory_search_tool(query: str, limit: int = 10) -> dict[str, Any]:
        return memory_search(store, query, limit)

    @server.tool()
    def memory_context_tool(prompt: str, max_items: int = 12) -> dict[str, Any]:
        return memory_context(store, prompt, max_items)

    @server.tool()
    def memory_read_tool(memory_id: str) -> dict[str, Any]:
        return memory_read(store, memory_id)

    @server.tool()
    def memory_write_tool(payload: dict[str, Any]) -> dict[str, Any]:
        return memory_write(store, queue, payload)

    return server


def main() -> None:
    build_server().run()
