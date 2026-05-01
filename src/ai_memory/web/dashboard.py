from __future__ import annotations

from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from ai_memory.core.config import default_config
from ai_memory.review.queue import ReviewQueue
from ai_memory.web.routes import create_memory_routes, create_memory_store, create_review_routes, create_stats_routes


def create_app(home: Path | None = None) -> FastAPI:
    app = FastAPI(title="ai-memory Dashboard")

    if home is not None:
        app.state.home = home
        config = default_config(home)
        store = create_memory_store(home)
        app.include_router(create_memory_routes(store))
        app.include_router(create_review_routes(ReviewQueue(config.review_queue_path), store))
        app.include_router(create_stats_routes(store))

    static_dir = Path(__file__).parent / "static"

    @app.get("/")
    async def root():
        return FileResponse(static_dir / "index.html")

    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    return app


def run_server(host: str = "127.0.0.1", port: int = 8080, home: Path | None = None) -> None:
    app = create_app(home=home)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
