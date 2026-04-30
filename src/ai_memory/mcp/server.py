from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_memory.retrieval.environment import detect_environment

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


def main() -> None:
    build_server().run()
