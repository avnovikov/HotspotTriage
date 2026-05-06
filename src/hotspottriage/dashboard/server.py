"""FastAPI dashboard server (daemon thread or ASGI test client)."""
from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import sys
import threading
import time
from typing import Any, AsyncGenerator

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse

from hotspottriage.dashboard.html import DASHBOARD_HTML
from hotspottriage.dashboard.log_handler import MemoryLogHandler
from hotspottriage.dashboard.stats import StatsCollector

BASE_PORT = 9123


def _find_free_port(host: str, base: int, *, span: int = 20) -> int:
    for port in range(base, base + span):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((host, port))
            except OSError:
                continue
            return port
    raise OSError(f"No free port found in range {base}–{base + span - 1}")


class DashboardServer:
    """Background FastAPI app exposing health, config, stats, logs, and SSE streams."""

    def __init__(
        self,
        config: dict[str, Any],
        stats: StatsCollector,
        log_handler: MemoryLogHandler,
        *,
        host: str = "127.0.0.1",
        base_port: int = BASE_PORT,
        open_on_start: bool = False,
    ) -> None:
        self._config = config
        self._stats = stats
        self._log_handler = log_handler
        self._host = host
        self._port = _find_free_port(host, base_port)
        self._open_on_start = bool(open_on_start)
        self._started_at = time.monotonic()
        self._app = self._build_app()
        self._thread: threading.Thread | None = None
        self._server: uvicorn.Server | None = None

    @property
    def app(self) -> FastAPI:
        return self._app

    @property
    def port(self) -> int:
        return self._port

    @property
    def base_url(self) -> str:
        return f"http://{self._host}:{self._port}"

    def _open_browser(self) -> None:
        url = f"{self.base_url}/dashboard/"
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import webbrowser; webbrowser.open(" + repr(url) + ")",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )

    def _build_app(self) -> FastAPI:
        app = FastAPI(title="HotspotTriage Dashboard", docs_url=None, redoc_url=None)
        stats_ref = self._stats
        log_ref = self._log_handler
        cfg_ref = self._config
        started = self._started_at

        @app.get("/api/health")
        def health() -> dict[str, Any]:
            return {
                "status": "alive",
                "uptime_s": round(time.monotonic() - started, 1),
            }

        @app.get("/api/config")
        def get_config() -> dict[str, Any]:
            return cfg_ref

        @app.get("/api/stats")
        def get_stats() -> dict[str, Any]:
            return stats_ref.get_snapshot()

        @app.post("/api/stats/clear")
        def clear_stats() -> dict[str, str]:
            stats_ref.clear()
            return {"status": "cleared"}

        @app.get("/api/logs")
        def get_logs(from_idx: int = 0) -> dict[str, Any]:
            lm = log_ref.get_log_messages(from_idx=from_idx)
            return {"messages": lm.messages, "max_idx": lm.max_idx}

        async def _log_sse() -> AsyncGenerator[str, None]:
            last_idx = 0
            while True:
                result = log_ref.get_log_messages(from_idx=last_idx)
                if result.messages:
                    for msg in result.messages:
                        yield "data: " + json.dumps(msg) + "\n\n"
                    last_idx = result.max_idx
                await asyncio.sleep(1.0)

        @app.get("/api/logs/stream")
        def log_stream() -> StreamingResponse:
            return StreamingResponse(_log_sse(), media_type="text/event-stream")

        async def _stats_sse() -> AsyncGenerator[str, None]:
            while True:
                snap = stats_ref.get_snapshot()
                yield "data: " + json.dumps(snap) + "\n\n"
                await asyncio.sleep(5.0)

        @app.get("/api/stats/stream")
        def stats_stream() -> StreamingResponse:
            return StreamingResponse(_stats_sse(), media_type="text/event-stream")

        @app.get("/dashboard/")
        def dashboard() -> HTMLResponse:
            return HTMLResponse(DASHBOARD_HTML)

        return app

    def start(self) -> None:
        if self._thread is not None:
            return
        config = uvicorn.Config(
            self._app,
            host=self._host,
            port=self._port,
            log_level="warning",
            loop="asyncio",
        )
        self._server = uvicorn.Server(config)

        def _run() -> None:
            assert self._server is not None
            asyncio.run(self._server.serve())

        self._thread = threading.Thread(
            target=_run,
            daemon=True,
            name="hotspottriage-dashboard",
        )
        self._thread.start()
        if self._open_on_start:
            self._open_browser()
