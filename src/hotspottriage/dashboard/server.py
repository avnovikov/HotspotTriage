"""FastAPI dashboard server (daemon thread or ASGI test client)."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import json
import logging
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import uvicorn
import yaml
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from hotspottriage import cache as _cache
from hotspottriage import config as _config
from hotspottriage import normalize as _normalize
from hotspottriage import score as _score_mod
from hotspottriage import stats as _stats_mod
from hotspottriage.discovery import is_git_url
from hotspottriage.dashboard.cache_http import CacheJob, slim_cache_job_result
from hotspottriage.dashboard.cache_jobs import find_free_port
from hotspottriage.dashboard.log_handler import MemoryLogHandler
from hotspottriage.dashboard.stats import StatsCollector
from hotspottriage.dashboard.cache_filter_fields import (
    compose_filter_from_fields,
    split_filter_for_fields,
)
from hotspottriage.username_privacy import redact_usernames_in_text

logger = logging.getLogger(__name__)

BASE_PORT = 9123

_DEFAULT_SCORE_METRICS = "churn_per_sloc,cyclomatic"


def _merge_config_overlay(
    base_doc: dict[str, Any],
    patch_doc: dict[str, Any],
    key: str,
) -> dict[str, Any]:
    """Deep-merge ``patch_doc[key]`` into the corresponding section of ``base_doc``."""
    patch_chunk = patch_doc.get(key)
    if not isinstance(patch_chunk, dict):
        return deepcopy(base_doc.get(key) or {})
    base_chunk = base_doc.get(key)
    if isinstance(base_chunk, dict):
        return _config._deep_merge(deepcopy(base_chunk), patch_chunk)
    return deepcopy(patch_chunk)


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
        self._base_snapshot = deepcopy(config)
        self._ensure_snapshot_defaults()
        self._stats = stats
        self._log_handler = log_handler
        bind_host = str(host).strip() if host is not None else ""
        self._host = bind_host or "127.0.0.1"
        self._port = find_free_port(self._host, base_port)
        self._open_on_start = bool(open_on_start)
        self._started_at = time.monotonic()
        self._cache_jobs: dict[str, CacheJob] = {}
        self._cache_jobs_lock = threading.Lock()
        self._state_file = Path(".hotspottriage") / "dashboard_state.json"
        self._state_lock = threading.Lock()
        self._config_patch_path = config_patch_path or (
            Path(".hotspottriage") / "dashboard_config_patch.yml"
        )
        self._patch_lock = threading.Lock()
        self._block_metrics_rows: list[dict[str, Any]] = []
        self._block_metrics_lock = threading.Lock()
        # Local repo whose ``.hotspottriage/`` config drives scoring (MCP/CLI parity).
        self._analysis_repo: Path | None = None
        self._app = self._build_app()
        self._thread: threading.Thread | None = None
        self._server: uvicorn.Server | None = None

    def _empty_local_state(self) -> dict[str, Any]:
        return {
            "last_target": "",
            "last_filter": "",
            "last_include": "",
            "last_exclude": "",
            "last_score_metrics": _DEFAULT_SCORE_METRICS,
            "recent_targets": [],
        }

    def _load_local_state_unlocked(self) -> dict[str, Any]:
        empty = self._empty_local_state()
        if not self._state_file.exists():
            return empty
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return empty
            merged = {**empty, **data}
            lf = str(merged.get("last_filter", "")).strip()
            li = str(merged.get("last_include", "")).strip()
            le = str(merged.get("last_exclude", "")).strip()
            if lf and not li and not le:
                merged["last_include"], merged["last_exclude"] = split_filter_for_fields(lf)
            elif (li or le) and not lf:
                merged["last_filter"] = compose_filter_from_fields(li, le) or ""
            return merged
        except Exception:
            return empty

    def _load_local_state(self) -> dict[str, Any]:
        with self._state_lock:
            return self._load_local_state_unlocked()

    def _enrich_cache_context_for_response(self, state: dict[str, Any]) -> dict[str, Any]:
        """Add UI-only redacted path fields; ``last_target`` on disk stays canonical."""
        out = dict(state)
        lt = str(out.get("last_target", "") or "").strip()
        out["last_target_display"] = redact_usernames_in_text(lt) if lt else ""
        rec = out.get("recent_targets")
        if isinstance(rec, list):
            out["recent_targets_display"] = [
                redact_usernames_in_text(str(x)) for x in rec if str(x).strip()
            ]
        else:
            out["recent_targets_display"] = []
        return out

    def _enrich_config_snapshot_for_ui(self, snap: dict[str, Any]) -> dict[str, Any]:
        """Add ``*_display`` strings for dashboard UI; canonical paths unchanged."""
        out = deepcopy(snap)
        proj = out.get("project")
        if isinstance(proj, dict):
            p = str(proj.get("path") or "").strip()
            if p:
                proj["path_display"] = redact_usernames_in_text(p)
        dash = out.get("dashboard")
        if isinstance(dash, dict):
            dt = str(dash.get("default_target") or "").strip()
            if dt:
                dash["default_target_display"] = redact_usernames_in_text(dt)
        return out

    def _ensure_snapshot_defaults(self) -> None:
        snap = self._base_snapshot
        if not isinstance(snap.get("metric_normalization"), dict):
            snap["metric_normalization"] = deepcopy(_config.DEFAULTS["metric_normalization"])
        if not isinstance(snap.get("score_aggregation"), dict):
            snap["score_aggregation"] = deepcopy(_config.DEFAULTS["score_aggregation"])

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
        if analysis_repo is not None:
            p = Path(analysis_repo).expanduser().resolve()
            if p.is_dir():
                self._analysis_repo = p
        scored_rows = self._derive_block_rows(rows)
        with self._block_metrics_lock:
            self._block_metrics_rows = scored_rows

    def _full_analyze_config_for_scoring(self) -> dict[str, Any]:
        """Merged config for block scoring / explanations (CLI + MCP parity)."""
        root = (
            self._analysis_repo
            if self._analysis_repo is not None
            else Path.cwd().resolve()
        )
        return _config.load_analyze_config_for_local_repo(root)

    def _derive_block_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Score raw block rows using the same merged config as CLI / MCP analyze."""
        merged = self._full_analyze_config_for_scoring()
        scored_rows: list[dict[str, Any]] = []
        raw_metric_keys = {
            "path",
            "sloc",
            "normalized_sloc",
            "cyclomatic",
            "halstead",
            "maintainability",
            "churn",
            "churn_per_sloc",
            "decayed_churn",
            "decayed_churn_per_sloc",
            "smell_count",
            "smell_severity",
            "smell_burden",
            "similarity_score",
            "match_count",
        }
        for row in rows:
            if not isinstance(row, dict):
                continue
            if raw_metric_keys <= set(row):
                scored_rows.extend(
                    _stats_mod.derive_block_score_rows(
                        [row],
                        merged,
                        score_metrics=list(merged.get("score_metrics") or []),
                        smell_weight=float(merged.get("smell_weight", 0.0)),
                        similarity_enabled=bool(merged.get("similarity_enabled", True)),
                    )
                )
            else:
                scored_rows.append(dict(row))
        return scored_rows

    def _load_patch_unlocked(self) -> dict[str, Any]:
        path = self._config_patch_path
        if not path.exists():
            return {}
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return {}
        if not text.strip():
            return {}
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError:
            return {}
        return data if isinstance(data, dict) else {}

    def _write_patch_unlocked(self, data: dict[str, Any]) -> None:
        self._config_patch_path.parent.mkdir(parents=True, exist_ok=True)
        self._config_patch_path.write_text(
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

    def _merged_snapshot(self) -> dict[str, Any]:
        """Base dashboard snapshot merged with persisted YAML overlay."""
        out = deepcopy(self._base_snapshot)
        patch = self._load_patch_unlocked()
        for key in ("metric_normalization", "score_aggregation", "proposed_models"):
            sub = patch.get(key)
            if isinstance(sub, dict):
                base_chunk = out.get(key)
                if isinstance(base_chunk, dict):
                    out[key] = _config._deep_merge(base_chunk, sub)
                else:
                    out[key] = deepcopy(sub)
        return out

    def _score_metrics_csv_for_cache_jobs(self) -> str:
        """Comma-separated product metrics for cache/status/generate (from config snapshot, not the UI)."""
        snap = self._merged_snapshot()
        raw = snap.get("score_metrics")
        if isinstance(raw, list) and raw:
            parts = [str(x).strip() for x in raw if str(x).strip()]
            if parts:
                return ",".join(parts)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        return _DEFAULT_SCORE_METRICS

    def _analysis_config_overrides(self, *, target: str | None = None) -> dict[str, Any]:
        """Return MN/SA overrides for cache generation (same repo layers as MCP analyze)."""
        if target and not is_git_url(target):
            cand = Path(target).expanduser().resolve()
            root = cand if cand.is_dir() else (
                self._analysis_repo or Path.cwd().resolve()
            )
        else:
            root = self._analysis_repo or Path.cwd().resolve()
        full = _config.load_analyze_config_for_local_repo(root)
        overrides: dict[str, Any] = {}
        for key in ("metric_normalization", "score_aggregation"):
            value = full.get(key)
            if isinstance(value, dict):
                overrides[key] = deepcopy(value)
        return overrides

    def _validate_merged_patch(self, merged_patch: dict[str, Any]) -> None:
        """Raise ``ValueError`` if overlay produces invalid normalization/score config."""
        probe = deepcopy(_config.DEFAULTS)
        for key in ("metric_normalization", "score_aggregation", "proposed_models"):
            probe[key] = _merge_config_overlay(self._base_snapshot, merged_patch, key)
        _normalize.validate_metric_normalization(probe)
        _score_mod.validate_score_aggregation(probe)
        _config._validate_proposed_models(probe)

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

    def _persist_cache_analysis_prefs(
        self,
        *,
        target: str,
        filt: str | None,
        include: str,
        exclude: str,
    ) -> None:
        score = self._score_metrics_csv_for_cache_jobs()
        filt_str = "" if filt is None else str(filt).strip()
        self._save_local_state(
            {
                "last_target": target,
                "last_filter": filt_str,
                "last_include": str(include).strip(),
                "last_exclude": str(exclude).strip(),
                "last_score_metrics": score,
            }
        )

    def _hydrate_block_metrics_when_missing(
        self, repo: Path, *, cache_file_exists: bool
    ) -> bool:
        """Populate live heatmap rows from MCP manager or disk when memory is empty."""
        with self._block_metrics_lock:
            has_rows = bool(self._block_metrics_rows)
        if not has_rows:
            try:
                from hotspottriage.mcp_server import _get_cache_manager

                mgr = _get_cache_manager(repo)
                live_rows = mgr.get_all_rows()
                if live_rows:
                    self.publish_latest_block_metrics(live_rows, analysis_repo=repo)
                    has_rows = True
            except Exception:
                logger.debug(
                    "Hydrating block metrics from MCP cache skipped",
                    exc_info=True,
                )
        if cache_file_exists and not has_rows:
            loaded_rows = _cache.load_block_results(repo)
            if loaded_rows:
                self.publish_latest_block_metrics(loaded_rows, analysis_repo=repo)
                has_rows = True
        return has_rows

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


# Backward-compatible names for tests and tooling.
_find_free_port = find_free_port
_slim_cache_job_result = slim_cache_job_result
