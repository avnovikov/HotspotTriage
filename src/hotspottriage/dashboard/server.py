"""FastAPI dashboard server (daemon thread or ASGI test client)."""
from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncGenerator

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse

from hotspottriage import cache as _cache
from hotspottriage.dashboard.heatmap import build_heatmap_fragment
from hotspottriage.dashboard.html import DASHBOARD_HTML
from hotspottriage.dashboard.log_handler import MemoryLogHandler
from hotspottriage.dashboard.stats import StatsCollector

BASE_PORT = 9123
RECENT_TARGETS_LIMIT = 15
LOG_STREAM_INTERVAL_S = 1.0
STATS_STREAM_INTERVAL_S = 5.0

# Sentinel words that the UI may send for "no value"; treated as empty string.
_FILTER_SENTINELS = frozenset({"none", "null", "<none>"})
_SCORE_SENTINELS = frozenset({"none", "null", "<default>"})


@dataclass
class CacheJob:
    job_id: str
    status: str
    progress: int
    message: str
    result: dict[str, Any] | None = None
    error: str | None = None


@dataclass(frozen=True)
class CacheRequest:
    """Normalized parameters extracted from a cache-related JSON payload.

    All fields are non-None strings; empty string means "unset".
    """

    target: str
    filt: str
    score: str

    @property
    def filter_or_none(self) -> str | None:
        return self.filt or None

    @property
    def score_or_none(self) -> str | None:
        return self.score or None


@dataclass(frozen=True)
class HeatmapOutcome:
    """Result of attempting to rebuild the heatmap fragment."""

    updated: bool
    error: str | None
    rows: int


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
        self._heatmap_lock = threading.Lock()
        self._heatmap_fragment = build_heatmap_fragment([])
        self._state_file = Path(".hotspottriage") / "dashboard_state.json"
        self._state_lock = threading.Lock()
        self._app = self._build_app()
        self._thread: threading.Thread | None = None
        self._server: uvicorn.Server | None = None

    # ----- local persisted state ------------------------------------------

    def _empty_local_state(self) -> dict[str, Any]:
        return {
            "last_target": "",
            "last_filter": "",
            "last_score_metrics": "",
            "recent_targets": [],
        }

    def _load_local_state_unlocked(self) -> dict[str, Any]:
        if not self._state_file.exists():
            return self._empty_local_state()
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
        except Exception:
            return self._empty_local_state()
        if not isinstance(data, dict):
            return self._empty_local_state()
        return data

    def _load_local_state(self) -> dict[str, Any]:
        with self._state_lock:
            return self._load_local_state_unlocked()

    def _save_local_state(self, updates: dict[str, Any]) -> dict[str, Any]:
        with self._state_lock:
            merged = {**self._load_local_state_unlocked(), **updates}
            merged["recent_targets"] = self._merge_recent_targets(merged)
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            self._state_file.write_text(json.dumps(merged, indent=2), encoding="utf-8")
            return merged

    @staticmethod
    def _merge_recent_targets(state: dict[str, Any]) -> list[str]:
        recent = [str(x) for x in (state.get("recent_targets") or []) if str(x).strip()]
        target = str(state.get("last_target", "")).strip()
        if not target:
            return recent
        deduped = [t for t in recent if t != target]
        deduped.insert(0, target)
        return deduped[:RECENT_TARGETS_LIMIT]

    # ----- payload normalization ------------------------------------------

    def _normalize_target(self, raw_target: str) -> str:
        target = str(raw_target).strip()
        if not target:
            return ""
        return str(Path(target).expanduser().resolve())

    @staticmethod
    def _normalize_optional(raw: Any, sentinels: frozenset[str]) -> str:
        """Return stripped text, or '' for None and any configured sentinel word."""
        if raw is None:
            return ""
        text = str(raw).strip()
        if text.lower() in sentinels:
            return ""
        return text

    def _normalize_filter(self, raw: Any) -> str:
        return self._normalize_optional(raw, _FILTER_SENTINELS)

    def _normalize_score_metrics(self, raw: Any) -> str:
        return self._normalize_optional(raw, _SCORE_SENTINELS)

    def _parse_cache_request(self, payload: dict[str, Any] | None) -> CacheRequest:
        """Validate, normalize, and persist a cache-endpoint payload.

        Raises HTTPException(400) when ``target`` is missing.
        """
        body = payload or {}
        target = self._normalize_target(body.get("target", ""))
        if not target:
            raise HTTPException(status_code=400, detail="target is required")
        request = CacheRequest(
            target=target,
            filt=self._normalize_filter(body.get("filter", "")),
            score=self._normalize_score_metrics(body.get("score_metrics", "")),
        )
        self._save_local_state(
            {
                "last_target": request.target,
                "last_filter": request.filt,
                "last_score_metrics": request.score,
            }
        )
        return request

    # ----- heatmap fragment management ------------------------------------

    def _set_heatmap_fragment(self, rows: list[Any]) -> None:
        with self._heatmap_lock:
            self._heatmap_fragment = build_heatmap_fragment(rows)

    def _rebuild_heatmap_from_cache(self, request: CacheRequest) -> HeatmapOutcome:
        """Rebuild the heatmap fragment from cache-backed block analysis."""
        try:
            from hotspottriage import mcp_server as _mcp_server

            raw = _mcp_server.analyze_with_cache(
                target=request.target,
                filter=request.filter_or_none,
                score_metrics=request.score_or_none,
            )
            payload = json.loads(raw)
            outcome = self._validate_block_payload(payload, request)
            if outcome is not None:
                return outcome
            rows = payload.get("results", [])
            self._set_heatmap_fragment(rows)
            return HeatmapOutcome(True, None, len(rows))
        except Exception as exc:  # pragma: no cover - defensive, non-fatal
            return HeatmapOutcome(False, str(exc), 0)

    @staticmethod
    def _validate_block_payload(
        payload: Any, request: CacheRequest
    ) -> HeatmapOutcome | None:
        """Return a failure outcome when the payload is unusable, else None."""
        if not isinstance(payload, dict):
            return HeatmapOutcome(False, "invalid response from analyze_with_cache", 0)
        if "error" in payload:
            return HeatmapOutcome(False, str(payload["error"]), 0)
        rows = payload.get("results", [])
        if not isinstance(rows, list):
            return HeatmapOutcome(False, "invalid results payload from analyze_with_cache", 0)
        if not rows:
            details = f"target={request.target}"
            if request.filt:
                details += f", filter={request.filt}"
            return HeatmapOutcome(False, f"no block rows returned ({details})", 0)
        return None

    @staticmethod
    def _heatmap_response(
        *,
        repo: Path,
        cache_dir: Path,
        exists: bool,
        outcome: HeatmapOutcome,
        extras: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response: dict[str, Any] = {
            "target": str(repo),
            "cache_dir": str(cache_dir),
            "exists": exists,
            "heatmap_updated": outcome.updated,
            "heatmap_error": outcome.error,
            "heatmap_rows": outcome.rows,
        }
        if extras:
            response.update(extras)
        return response

    # ----- cache job state ------------------------------------------------

    def _create_cache_job(self, target: str) -> CacheJob:
        job = CacheJob(
            job_id=str(uuid.uuid4()),
            status="running",
            progress=5,
            message=f"Starting cache generation for {target}",
        )
        with self._cache_jobs_lock:
            self._cache_jobs[job.job_id] = job
        return job

    def _update_job(self, job_id: str, **fields: Any) -> None:
        with self._cache_jobs_lock:
            job = self._cache_jobs.get(job_id)
            if job is None:
                return
            for name, value in fields.items():
                setattr(job, name, value)

    def _run_cache_job(self, job_id: str, request: CacheRequest) -> None:
        # Local import avoids circular dependency with mcp_server.
        from hotspottriage import cache_generator as _cache_generator

        try:
            self._update_job(job_id, progress=30, message="Generating block cache...")
            result = _cache_generator.generate_full_cache(
                target=request.target,
                filter=request.filter_or_none,
                score_metrics=request.score_or_none,
                verbose=False,
            )
            block_results = result.get("blocks", {}).get("results", [])
            if isinstance(block_results, list):
                self._set_heatmap_fragment(block_results)
            self._update_job(
                job_id,
                status="done",
                progress=100,
                message="Cache generation complete",
                result=result,
            )
        except Exception as exc:
            self._update_job(
                job_id,
                status="error",
                progress=100,
                message="Cache generation failed",
                error=str(exc),
            )

    def _start_cache_job(self, request: CacheRequest) -> CacheJob:
        job = self._create_cache_job(request.target)
        threading.Thread(
            target=self._run_cache_job,
            args=(job.job_id, request),
            daemon=True,
            name=f"cache-job-{job.job_id[:8]}",
        ).start()
        return job

    # ----- cache endpoint handlers ----------------------------------------

    def _handle_cache_status(self, payload: dict[str, Any] | None) -> dict[str, Any]:
        request = self._parse_cache_request(payload)
        repo = Path(request.target)
        cache_dir = _cache.cache_path_for(repo)
        cache_file = cache_dir / "blocks.pkl"
        metadata = _cache.Cache(repo).get_metadata()
        exists = cache_file.exists()
        size = cache_file.stat().st_size if exists else 0
        entries = metadata.get("entry_count", 0) if isinstance(metadata, dict) else 0
        outcome = (
            self._rebuild_heatmap_from_cache(request)
            if exists
            else HeatmapOutcome(False, None, 0)
        )
        return self._heatmap_response(
            repo=repo,
            cache_dir=cache_dir,
            exists=exists,
            outcome=outcome,
            extras={
                "entries": int(entries),
                "size_bytes": int(size),
                "metadata": metadata,
            },
        )

    def _handle_rebuild_heatmap(self, payload: dict[str, Any] | None) -> dict[str, Any]:
        request = self._parse_cache_request(payload)
        repo = Path(request.target)
        cache_dir = _cache.cache_path_for(repo)
        cache_exists = (cache_dir / "blocks.pkl").exists()
        if not cache_exists:
            return self._heatmap_response(
                repo=repo,
                cache_dir=cache_dir,
                exists=False,
                outcome=HeatmapOutcome(False, "cache file not found", 0),
            )
        return self._heatmap_response(
            repo=repo,
            cache_dir=cache_dir,
            exists=True,
            outcome=self._rebuild_heatmap_from_cache(request),
        )

    def _handle_generate_cache(self, payload: dict[str, Any] | None) -> dict[str, Any]:
        request = self._parse_cache_request(payload)
        job = self._start_cache_job(request)
        return {"job_id": job.job_id, "status": "running", "target": request.target}

    def _read_cache_job(self, job_id: str) -> dict[str, Any]:
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

    def _read_heatmap_fragment(self) -> str:
        with self._heatmap_lock:
            return self._heatmap_fragment

    # ----- properties / lifecycle -----------------------------------------

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

    # ----- app builder ----------------------------------------------------

    def _build_app(self) -> FastAPI:
        app = FastAPI(title="HotspotTriage Dashboard", docs_url=None, redoc_url=None)
        self._register_health_routes(app)
        self._register_cache_routes(app)
        self._register_heatmap_routes(app)
        self._register_observability_routes(app)
        self._register_dashboard_route(app)
        return app

    def _register_health_routes(self, app: FastAPI) -> None:
        started = self._started_at
        cfg_ref = self._config

        @app.get("/api/health")
        def health() -> dict[str, Any]:
            return {
                "status": "alive",
                "uptime_s": round(time.monotonic() - started, 1),
            }

        @app.get("/api/config")
        def get_config() -> dict[str, Any]:
            return cfg_ref

    def _register_cache_routes(self, app: FastAPI) -> None:
        @app.get("/api/cache/context")
        def get_cache_context() -> dict[str, Any]:
            return self._load_local_state()

        @app.post("/api/cache/context")
        def set_cache_context(payload: dict[str, Any] | None = None) -> dict[str, Any]:
            body = payload or {}
            return self._save_local_state(
                {
                    "last_target": self._normalize_target(body.get("target", "")),
                    "last_filter": str(body.get("filter", "")).strip(),
                    "last_score_metrics": self._normalize_score_metrics(
                        body.get("score_metrics", "")
                    ),
                }
            )

        @app.post("/api/cache/status")
        def cache_status(payload: dict[str, Any] | None = None) -> dict[str, Any]:
            return self._handle_cache_status(payload)

        @app.post("/api/cache/generate")
        def generate_cache(payload: dict[str, Any] | None = None) -> dict[str, Any]:
            return self._handle_generate_cache(payload)

        @app.get("/api/cache/jobs/{job_id}")
        def cache_job_status(job_id: str) -> dict[str, Any]:
            return self._read_cache_job(job_id)

    def _register_heatmap_routes(self, app: FastAPI) -> None:
        @app.post("/api/heatmap/rebuild")
        def rebuild_heatmap(payload: dict[str, Any] | None = None) -> dict[str, Any]:
            return self._handle_rebuild_heatmap(payload)

        @app.get("/api/heatmap/fragment")
        def get_heatmap_fragment() -> HTMLResponse:
            response = HTMLResponse(self._read_heatmap_fragment())
            response.headers["Cache-Control"] = "no-store, max-age=0"
            return response

    def _register_observability_routes(self, app: FastAPI) -> None:
        stats_ref = self._stats
        log_ref = self._log_handler

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
                await asyncio.sleep(LOG_STREAM_INTERVAL_S)

        @app.get("/api/logs/stream")
        def log_stream() -> StreamingResponse:
            return StreamingResponse(_log_sse(), media_type="text/event-stream")

        async def _stats_sse() -> AsyncGenerator[str, None]:
            while True:
                yield "data: " + json.dumps(stats_ref.get_snapshot()) + "\n\n"
                await asyncio.sleep(STATS_STREAM_INTERVAL_S)

        @app.get("/api/stats/stream")
        def stats_stream() -> StreamingResponse:
            return StreamingResponse(_stats_sse(), media_type="text/event-stream")

    def _register_dashboard_route(self, app: FastAPI) -> None:
        @app.get("/dashboard/")
        def dashboard() -> HTMLResponse:
            return HTMLResponse(DASHBOARD_HTML)

    # ----- start ----------------------------------------------------------

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

        def _serve() -> None:
            assert self._server is not None
            asyncio.run(self._server.serve())

        self._thread = threading.Thread(
            target=_serve,
            daemon=True,
            name="hotspottriage-dashboard",
        )
        self._thread.start()
        if self._open_on_start:
            self._open_browser()
