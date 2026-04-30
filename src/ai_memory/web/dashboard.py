from __future__ import annotations

from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse


def create_app(home: Optional[Path] = None) -> FastAPI:
    app = FastAPI(title="ai-memory Dashboard")

    static_dir = Path(__file__).parent / "static"

    @app.get("/")
    async def root():
        return FileResponse(static_dir / "index.html")

    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    return app


def run_server(host: str = "127.0.0.1", port: int = 8080) -> None:
    app = create_app()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
