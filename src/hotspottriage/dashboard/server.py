"""FastAPI dashboard server (daemon thread or ASGI test client)."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from hotspottriage.dashboard.block_metrics_store import BlockMetricsStore
from hotspottriage.dashboard.cache_http import CacheJob, slim_cache_job_result
from hotspottriage.dashboard.cache_jobs import find_free_port
from hotspottriage.dashboard.config_patch_store import ConfigPatchStore
from hotspottriage.dashboard.local_state import DEFAULT_SCORE_METRICS, DashboardLocalState
from hotspottriage.dashboard.log_handler import MemoryLogHandler
from hotspottriage.dashboard.stats import StatsCollector

BASE_PORT = 9123


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
        config_patch_path: Path | None = None,
    ) -> None:
        self._stats = stats
        self._log_handler = log_handler
        bind_host = str(host).strip() if host is not None else ""
        self._host = bind_host or "127.0.0.1"
        self._port = find_free_port(self._host, base_port)
        self._open_on_start = bool(open_on_start)
        self._started_at = time.monotonic()
        self._cache_jobs: dict[str, CacheJob] = {}
        self._cache_jobs_lock = threading.Lock()
        self._patch_lock = threading.Lock()
        patch_path = config_patch_path or (
            Path(".hotspottriage") / "dashboard_config_patch.yml"
        )
        self._config_patch = ConfigPatchStore(deepcopy(config), patch_path)
        self._config_patch.ensure_defaults()
        self._local_state = DashboardLocalState(
            Path(".hotspottriage") / "dashboard_state.json",
            threading.Lock(),
        )
        self.block_store = BlockMetricsStore()
        self._app = self._build_app()
        self._thread: threading.Thread | None = None
        self._server: uvicorn.Server | None = None

    @property
    def _state_file(self) -> Path:
        """Tests may assign to redirect persisted dashboard state to a temp path."""
        return self._local_state._state_file

    @_state_file.setter
    def _state_file(self, path: Path) -> None:
        self._local_state = DashboardLocalState(
            path, self._local_state.lock, default_score_metrics=DEFAULT_SCORE_METRICS
        )

    def publish_latest_block_metrics(
        self,
        rows: list[dict[str, Any]],
        *,
        analysis_repo: Path | None = None,
    ) -> None:
        """Replace stored raw block rows used by distribution histograms.

        When *analysis_repo* is set (e.g. MCP ``analyze``), derived scores and
        lazy narratives use :func:`config.load_analyze_config_for_local_repo`
        for that path — same as CLI and MCP for that checkout.
        """
        self.block_store.publish(rows, analysis_repo=analysis_repo)

    def _full_analyze_config_for_scoring(self) -> dict[str, Any]:
        return self.block_store.full_analyze_config_for_scoring()

    def _analysis_config_overrides(self, *, target: str | None = None) -> dict[str, Any]:
        return self.block_store.analysis_config_overrides(target=target)

    def _hydrate_block_metrics_when_missing(
        self, repo: Path, *, cache_file_exists: bool
    ) -> bool:
        return self.block_store.hydrate_when_missing(repo, cache_file_exists=cache_file_exists)

    def _merged_snapshot(self) -> dict[str, Any]:
        return self._config_patch.merged_snapshot()

    def _score_metrics_csv_for_cache_jobs(self) -> str:
        return self._config_patch.score_metrics_csv_for_cache_jobs()

    def _validate_merged_patch(self, merged_patch: dict[str, Any]) -> None:
        self._config_patch.validate_merged_patch(merged_patch)

    def _load_patch_unlocked(self) -> dict[str, Any]:
        return self._config_patch.load_patch_unlocked()

    def _write_patch_unlocked(self, data: dict[str, Any]) -> None:
        self._config_patch.write_patch_unlocked(data)

    def _enrich_config_snapshot_for_ui(self, snap: dict[str, Any]) -> dict[str, Any]:
        return self._config_patch.enrich_snapshot_for_ui(snap)

    def _load_local_state(self) -> dict[str, Any]:
        return self._local_state.load()

    def _enrich_cache_context_for_response(self, state: dict[str, Any]) -> dict[str, Any]:
        return self._local_state.enrich_cache_context_for_response(state)

    def _save_local_state(self, updates: dict[str, Any]) -> dict[str, Any]:
        return self._local_state.save(updates)

    def _persist_cache_analysis_prefs(
        self,
        *,
        target: str,
        filt: str | None,
        include: str,
        exclude: str,
    ) -> None:
        self._local_state.persist_cache_analysis_prefs(
            target=target,
            filt=filt,
            include=include,
            exclude=exclude,
            last_score_metrics=self._score_metrics_csv_for_cache_jobs(),
        )

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
        from hotspottriage.dashboard.routes.api import build_dashboard_api_router
        from hotspottriage.dashboard.routes.pages import router as pages_router

        app = FastAPI(title="HotspotTriage Dashboard", docs_url=None, redoc_url=None)

        _static_dir = Path(__file__).resolve().parent / "static"
        app.mount(
            "/dashboard/static",
            StaticFiles(directory=str(_static_dir)),
            name="dashboard-static",
        )

        app.include_router(pages_router)
        app.include_router(build_dashboard_api_router(self))
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
