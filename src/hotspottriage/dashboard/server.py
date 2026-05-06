"""FastAPI dashboard server (daemon thread or ASGI test client)."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import socket
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse

from hotspottriage import cache as _cache
from hotspottriage.dashboard.html import DASHBOARD_HTML
from hotspottriage.dashboard.log_handler import MemoryLogHandler
from hotspottriage.dashboard.stats import StatsCollector

BASE_PORT = 9123


@dataclass
class CacheJob:
    job_id: str
    status: str
    progress: int
    message: str
    result: dict[str, Any] | None = None
    error: str | None = None


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
        self._cache_jobs: dict[str, CacheJob] = {}
        self._cache_jobs_lock = threading.Lock()
        self._state_file = Path(".hotspottriage") / "dashboard_state.json"
        self._state_lock = threading.Lock()
        self._app = self._build_app()
        self._thread: threading.Thread | None = None
        self._server: uvicorn.Server | None = None

    def _empty_local_state(self) -> dict[str, Any]:
        return {
            "last_target": "",
            "last_filter": "",
            "last_score_metrics": "churn_per_sloc,cyclomatic",
            "recent_targets": [],
        }

    def _load_local_state_unlocked(self) -> dict[str, Any]:
        if not self._state_file.exists():
            return self._empty_local_state()
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return self._empty_local_state()
            return data
        except Exception:
            return self._empty_local_state()

    def _load_local_state(self) -> dict[str, Any]:
        with self._state_lock:
            return self._load_local_state_unlocked()

    def _save_local_state(self, updates: dict[str, Any]) -> dict[str, Any]:
        with self._state_lock:
            base = self._load_local_state_unlocked()
            merged = {**base, **updates}
            tgt = str(merged.get("last_target", "")).strip()
            rec = [str(x) for x in (merged.get("recent_targets") or []) if str(x).strip()]
            if tgt:
                rec = [t for t in rec if t != tgt]
                rec.insert(0, tgt)
                rec = rec[:15]
            merged["recent_targets"] = rec
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            self._state_file.write_text(json.dumps(merged, indent=2), encoding="utf-8")
            return merged

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

        @app.get("/api/cache/context")
        def get_cache_context() -> dict[str, Any]:
            return self._load_local_state()

        @app.post("/api/cache/context")
        def set_cache_context(payload: dict[str, Any] | None = None) -> dict[str, Any]:
            body = payload or {}
            updates = {
                "last_target": str(body.get("target", "")).strip(),
                "last_filter": str(body.get("filter", "")).strip(),
                "last_score_metrics": str(
                    body.get("score_metrics", "churn_per_sloc,cyclomatic")
                ).strip()
                or "churn_per_sloc,cyclomatic",
            }
            return self._save_local_state(updates)

        @app.post("/api/cache/status")
        def cache_status(payload: dict[str, Any] | None = None) -> dict[str, Any]:
            body = payload or {}
            target = str(body.get("target", "")).strip()
            if not target:
                raise HTTPException(status_code=400, detail="target is required")
            filt = str(body.get("filter", "")).strip()
            score = str(body.get("score_metrics", "churn_per_sloc,cyclomatic")).strip()
            self._save_local_state(
                {
                    "last_target": target,
                    "last_filter": filt,
                    "last_score_metrics": score or "churn_per_sloc,cyclomatic",
                }
            )
            repo = Path(target).resolve()
            cache_dir = _cache.cache_path_for(repo)
            cache_file = cache_dir / "blocks.pkl"
            metadata = _cache.Cache(repo).get_metadata()
            exists = cache_file.exists()
            size = cache_file.stat().st_size if exists else 0
            entries = metadata.get("entry_count", 0) if isinstance(metadata, dict) else 0
            return {
                "target": str(repo),
                "cache_dir": str(cache_dir),
                "exists": exists,
                "entries": int(entries),
                "size_bytes": int(size),
                "metadata": metadata,
            }

        @app.post("/api/cache/generate")
        def generate_cache(payload: dict[str, Any] | None = None) -> dict[str, Any]:
            # Local import avoids circular dependency with mcp_server.
            from hotspottriage import cache_generator as _cache_generator

            body = payload or {}
            target = str(body.get("target", "")).strip()
            if not target:
                raise HTTPException(status_code=400, detail="target is required")
            filt = None if body.get("filter") in (None, "") else str(body.get("filter"))
            score = str(body.get("score_metrics", "churn_per_sloc,cyclomatic"))
            self._save_local_state(
                {
                    "last_target": target,
                    "last_filter": "" if filt is None else filt,
                    "last_score_metrics": score,
                }
            )
            job_id = str(uuid.uuid4())
            job = CacheJob(
                job_id=job_id,
                status="running",
                progress=5,
                message=f"Starting cache generation for {target}",
            )
            with self._cache_jobs_lock:
                self._cache_jobs[job_id] = job

            def _run() -> None:
                try:
                    with self._cache_jobs_lock:
                        self._cache_jobs[job_id].progress = 30
                        self._cache_jobs[job_id].message = "Generating block cache..."
                    result = _cache_generator.generate_full_cache(
                        target=target,
                        filter=filt,
                        score_metrics=score,
                        verbose=False,
                    )
                    with self._cache_jobs_lock:
                        self._cache_jobs[job_id].status = "done"
                        self._cache_jobs[job_id].progress = 100
                        self._cache_jobs[job_id].message = "Cache generation complete"
                        self._cache_jobs[job_id].result = result
                except Exception as e:
                    with self._cache_jobs_lock:
                        self._cache_jobs[job_id].status = "error"
                        self._cache_jobs[job_id].progress = 100
                        self._cache_jobs[job_id].message = "Cache generation failed"
                        self._cache_jobs[job_id].error = str(e)

            threading.Thread(target=_run, daemon=True, name=f"cache-job-{job_id[:8]}").start()
            return {"job_id": job_id, "status": "running"}

        @app.get("/api/cache/jobs/{job_id}")
        def cache_job_status(job_id: str) -> dict[str, Any]:
            with self._cache_jobs_lock:
                job = self._cache_jobs.get(job_id)
                if job is None:
                    raise HTTPException(status_code=404, detail="cache job not found")
                return {
                    "job_id": job.job_id,
                    "status": job.status,
                    "progress": job.progress,
                    "message": job.message,
                    "error": job.error,
                    "result": job.result,
                }

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
