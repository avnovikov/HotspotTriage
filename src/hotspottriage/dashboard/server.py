"""FastAPI dashboard server (daemon thread or ASGI test client)."""
from __future__ import annotations

import asyncio
from copy import deepcopy
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
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse

from hotspottriage import cache as _cache
from hotspottriage import config as _config
from hotspottriage import normalize as _normalize
from hotspottriage import score as _score_mod
from hotspottriage.dashboard.html import DASHBOARD_HTML
from hotspottriage.dashboard.log_handler import MemoryLogHandler
from hotspottriage.dashboard.stats import StatsCollector

BASE_PORT = 9123

# Numeric Statistic fields eligible for /api/stats/distribution histograms.
_DISTRIBUTION_METRICS: frozenset[str] = frozenset(
    {
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
        "score",
    }
)

# Upper cap for ``/api/stats/heatmap`` limit (query param).
_HEATMAP_MAX_LIMIT = 500


def _slim_cache_job_result(result: dict[str, Any]) -> dict[str, Any]:
    """Strip huge ``results`` lists before storing on the cache job.

    The dashboard poll endpoint returns ``job.result`` as JSON; including
    hundreds of full block/class rows can exceed what browsers reliably parse
    or hold in memory. Rows are already applied via ``publish_latest_block_metrics``.
    """
    out: dict[str, Any] = {
        "timestamp": result.get("timestamp"),
        "target": result.get("target"),
        "filter": result.get("filter"),
        "score_metrics": result.get("score_metrics"),
        "metadata": dict(result.get("metadata") or {}),
        "cache_status": dict(result.get("cache_status") or {}),
    }
    blocks = result.get("blocks")
    if isinstance(blocks, dict):
        slim_b = {k: v for k, v in blocks.items() if k != "results"}
        res = blocks.get("results")
        if isinstance(res, list) and "count" not in slim_b:
            slim_b["count"] = len(res)
        out["blocks"] = slim_b
    classes = result.get("classes")
    if isinstance(classes, dict):
        slim_c = {k: v for k, v in classes.items() if k != "results"}
        res = classes.get("results")
        if isinstance(res, list) and "count" not in slim_c:
            slim_c["count"] = len(res)
        out["classes"] = slim_c
    return out


def _normalize_cache_target(raw_target: str) -> str:
    """Normalize cache target paths so ``./`` inputs persist as absolute paths."""
    target = str(raw_target).strip()
    if not target:
        return ""
    if "://" in target or target.startswith("git@"):
        return target
    try:
        return str(Path(target).expanduser().resolve())
    except OSError:
        return target


_HEATMAP_SCORE_COLUMNS: tuple[str, ...] = (
    "score",
    "complexity_burden",
    "churn_burden",
    "maintainability_burden",
    "smell_burden",
    "similarity_burden",
)


def _split_block_path(raw_path: str) -> tuple[str, str]:
    path = str(raw_path).strip()
    if not path:
        return "", ""
    if "::" not in path:
        return path, ""
    file_path, symbol = path.split("::", 1)
    return file_path, symbol


def _as_float_or_zero(raw: Any) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _build_heatmap_rows(rows: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    """Return matrix rows sorted by file score, then method score."""
    table_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        path = row.get("path")
        if not path:
            continue
        file_path, method_name = _split_block_path(str(path))
        subs = row.get("score_subscores")
        subs_map = subs if isinstance(subs, dict) else {}
        item: dict[str, Any] = {
            "path": str(path),
            "file": file_path,
            "method": method_name,
        }
        for col in _HEATMAP_SCORE_COLUMNS:
            value = row.get(col)
            if value is None:
                value = subs_map.get(col)
            item[col] = _as_float_or_zero(value)
        band = row.get("score_band")
        if band is not None and str(band).strip():
            item["score_band"] = str(band)
        table_rows.append(item)

    file_max_score: dict[str, float] = {}
    for row in table_rows:
        file_name = str(row["file"])
        score = _as_float_or_zero(row.get("score"))
        prev = file_max_score.get(file_name)
        if prev is None or score > prev:
            file_max_score[file_name] = score

    table_rows.sort(
        key=lambda r: (
            -file_max_score.get(str(r["file"]), 0.0),
            str(r["file"]),
            -_as_float_or_zero(r.get("score")),
            str(r["method"]),
        )
    )
    return table_rows[:limit]


def _heatmap_column_maxima(
    table_rows: list[dict[str, Any]], *, columns: tuple[str, ...]
) -> dict[str, float]:
    """Per-column maxima for heatmap cell tinting.

    Excludes meta rows whose ``path`` starts with ``__`` (e.g. similarity aggregate),
    which often have an outsized ``score`` and would flatten tinting for real blocks.
    """
    eligible = [r for r in table_rows if not str(r.get("path", "")).startswith("__")]
    if not eligible:
        eligible = table_rows
    out: dict[str, float] = {}
    for col in columns:
        vals = [_as_float_or_zero(r.get(col)) for r in eligible]
        m = float(max(vals)) if vals else 0.0
        out[col] = m if m > 0 else 1e-9
    return out


def _histogram_buckets(values: list[float], *, bins: int = 20) -> tuple[list[list[float]], list[int]]:
    """Return ``buckets`` as ``[low, high]`` pairs and ``counts`` (same length)."""
    if not values:
        return [], []
    if bins < 1:
        raise ValueError("bins must be positive")
    vmin = float(min(values))
    vmax = float(max(values))
    if vmin == vmax:
        return [[vmin, vmax]], [len(values)]
    width = (vmax - vmin) / bins
    counts = [0] * bins
    buckets: list[list[float]] = []
    for i in range(bins):
        lo = vmin + i * width
        hi = vmin + (i + 1) * width
        if i == bins - 1:
            hi = vmax
        buckets.append([lo, hi])
    for v in values:
        fv = float(v)
        if fv >= vmax:
            idx = bins - 1
        elif fv <= vmin:
            idx = 0
        else:
            idx = int((fv - vmin) / width)
            if idx >= bins:
                idx = bins - 1
        counts[idx] += 1
    return buckets, counts


@dataclass
class CacheJob:
    job_id: str
    status: str
    progress: int
    message: str
    started_at_monotonic: float
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
        config_patch_path: Path | None = None,
    ) -> None:
        self._base_snapshot = deepcopy(config)
        self._ensure_snapshot_defaults()
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
        self._config_patch_path = config_patch_path or (
            Path(".hotspottriage") / "dashboard_config_patch.yml"
        )
        self._patch_lock = threading.Lock()
        self._block_metrics_rows: list[dict[str, Any]] = []
        self._block_metrics_lock = threading.Lock()
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

    def _ensure_snapshot_defaults(self) -> None:
        snap = self._base_snapshot
        if not isinstance(snap.get("metric_normalization"), dict):
            snap["metric_normalization"] = deepcopy(_config.DEFAULTS["metric_normalization"])
        if not isinstance(snap.get("score_aggregation"), dict):
            snap["score_aggregation"] = deepcopy(_config.DEFAULTS["score_aggregation"])

    def publish_latest_block_metrics(self, rows: list[dict[str, Any]]) -> None:
        """Replace stored raw block rows used by distribution histograms."""
        with self._block_metrics_lock:
            self._block_metrics_rows = list(rows)

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
        mn_patch = patch.get("metric_normalization")
        if isinstance(mn_patch, dict):
            mn_base = out.get("metric_normalization")
            if isinstance(mn_base, dict):
                out["metric_normalization"] = _config._deep_merge(mn_base, mn_patch)
            else:
                out["metric_normalization"] = deepcopy(mn_patch)
        sa_patch = patch.get("score_aggregation")
        if isinstance(sa_patch, dict):
            sa_base = out.get("score_aggregation")
            if isinstance(sa_base, dict):
                out["score_aggregation"] = _config._deep_merge(sa_base, sa_patch)
            else:
                out["score_aggregation"] = deepcopy(sa_patch)
        return out

    def _validate_merged_patch(self, merged_patch: dict[str, Any]) -> None:
        """Raise ``ValueError`` if overlay produces invalid normalization/score config."""
        probe = deepcopy(_config.DEFAULTS)
        mn_base = deepcopy(self._base_snapshot.get("metric_normalization") or {})
        mn_patch = merged_patch.get("metric_normalization")
        if isinstance(mn_patch, dict):
            mn_full = _config._deep_merge(mn_base, mn_patch)
        else:
            mn_full = mn_base
        probe["metric_normalization"] = mn_full

        sa_base = deepcopy(self._base_snapshot.get("score_aggregation") or {})
        sa_patch = merged_patch.get("score_aggregation")
        if isinstance(sa_patch, dict):
            sa_full = _config._deep_merge(sa_base, sa_patch)
        else:
            sa_full = sa_base
        probe["score_aggregation"] = sa_full

        _normalize.validate_metric_normalization(probe)
        _score_mod.validate_score_aggregation(probe)

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
        dash_self = self
        started = self._started_at

        @app.get("/api/health")
        def health() -> dict[str, Any]:
            return {
                "status": "alive",
                "uptime_s": round(time.monotonic() - started, 1),
            }

        @app.get("/api/config")
        def get_config() -> dict[str, Any]:
            return dash_self._merged_snapshot()

        @app.post("/api/config/patch")
        def patch_config(payload: dict[str, Any] | None = None) -> dict[str, Any]:
            body = payload if isinstance(payload, dict) else {}
            allowed = {"metric_normalization", "score_aggregation"}
            extra = set(body.keys()) - allowed
            if extra:
                raise HTTPException(
                    status_code=400,
                    detail=f"unsupported patch key(s): {sorted(extra)}",
                )
            if not body:
                raise HTTPException(
                    status_code=400,
                    detail="patch body must include metric_normalization and/or score_aggregation",
                )
            with dash_self._patch_lock:
                current = dash_self._load_patch_unlocked()
                merged_file = _config._deep_merge(current, body)
                try:
                    dash_self._validate_merged_patch(merged_file)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e)) from e
                dash_self._write_patch_unlocked(merged_file)
            return {"status": "ok", "merged_keys": sorted(body.keys())}

        @app.get("/api/stats/heatmap")
        def stats_heatmap(
            limit: int = 500,
        ) -> dict[str, Any]:
            if not isinstance(limit, int) or isinstance(limit, bool):
                raise HTTPException(
                    status_code=400,
                    detail="limit must be an integer",
                )
            if limit < 1:
                raise HTTPException(status_code=400, detail="limit must be >= 1")
            if limit > _HEATMAP_MAX_LIMIT:
                raise HTTPException(
                    status_code=400,
                    detail=f"limit must be <= {_HEATMAP_MAX_LIMIT}",
                )
            with dash_self._block_metrics_lock:
                raw_rows = list(dash_self._block_metrics_rows)
            rows = _build_heatmap_rows(raw_rows, limit=limit)
            column_maxima = _heatmap_column_maxima(
                rows, columns=_HEATMAP_SCORE_COLUMNS
            )
            return {
                "limit": limit,
                "columns": list(_HEATMAP_SCORE_COLUMNS),
                "rows": rows,
                "column_maxima": column_maxima,
            }

        @app.get("/api/stats/distribution")
        def stats_distribution(metric: str = "") -> dict[str, Any]:
            name = str(metric).strip()
            if not name:
                return {"metric": "", "buckets": [], "counts": []}
            if name not in _DISTRIBUTION_METRICS:
                return {"metric": name, "buckets": [], "counts": []}
            with dash_self._block_metrics_lock:
                rows = list(dash_self._block_metrics_rows)
            values: list[float] = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                raw = row.get(name)
                if raw is None:
                    continue
                try:
                    values.append(float(raw))
                except (TypeError, ValueError):
                    continue
            if not values:
                return {"metric": name, "buckets": [], "counts": []}
            buckets, counts = _histogram_buckets(values)
            return {"metric": name, "buckets": buckets, "counts": counts}

        @app.get("/api/cache/context")
        def get_cache_context() -> dict[str, Any]:
            return self._load_local_state()

        @app.post("/api/cache/context")
        def set_cache_context(payload: dict[str, Any] | None = None) -> dict[str, Any]:
            body = payload or {}
            updates = {
                "last_target": _normalize_cache_target(body.get("target", "")),
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
            target = _normalize_cache_target(body.get("target", ""))
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
            cache_file = cache_dir / _cache._CACHE_FILE
            metadata = _cache.get_metadata(repo)
            exists = cache_file.exists()
            size = cache_file.stat().st_size if exists else 0
            entries = metadata.get("entry_count", 0) if isinstance(metadata, dict) else 0
            with self._block_metrics_lock:
                has_rows = bool(self._block_metrics_rows)
            if not has_rows:
                # Try live manager rows first, then fall back to disk.
                try:
                    from hotspottriage.mcp_server import _get_cache_manager
                    mgr = _get_cache_manager(repo)
                    live_rows = mgr.get_all_rows()
                    if live_rows:
                        self.publish_latest_block_metrics(live_rows)
                        has_rows = True
                except Exception:
                    pass
            if exists and not has_rows:
                loaded = _cache.load_block_results(repo)
                if loaded:
                    self.publish_latest_block_metrics(loaded)
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
            target = _normalize_cache_target(body.get("target", ""))
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
                started_at_monotonic=time.monotonic(),
            )
            with self._cache_jobs_lock:
                self._cache_jobs[job_id] = job

            dash_self = self

            def _cache_progress(label: str, done: int, total: int) -> None:
                t = max(int(total), 1)
                d = min(max(int(done), 0), t)
                if label.startswith("Scanning "):
                    msg = label
                    pct = 26 + int(24 * d / t)
                elif label.startswith("Block churn"):
                    msg = f"Block churn (git log -L) {d}/{t}"
                    pct = 50 + int(18 * d / t)
                elif label.startswith("Building block rows"):
                    msg = "Assembling block rows…" if d == 0 else label
                    pct = 70 + int(12 * d / t)
                elif "::" in label:
                    msg = label
                    pct = 72 + int(14 * d / t)
                elif label.startswith("Indexing "):
                    msg = label
                    pct = 86 + int(9 * d / t)
                else:
                    msg = label
                    pct = 40
                with dash_self._cache_jobs_lock:
                    job = dash_self._cache_jobs.get(job_id)
                    if job is None:
                        return
                    job.message = msg
                    job.progress = min(96, max(job.progress, pct))

            def _run() -> None:
                try:
                    with self._cache_jobs_lock:
                        self._cache_jobs[job_id].progress = 8
                        self._cache_jobs[job_id].message = "Starting…"
                    result = _cache_generator.generate_full_cache(
                        target=target,
                        filter=filt,
                        score_metrics=score,
                        verbose=False,
                        progress_callback=_cache_progress,
                    )
                    with self._cache_jobs_lock:
                        self._cache_jobs[job_id].status = "done"
                        self._cache_jobs[job_id].progress = 100
                        self._cache_jobs[job_id].message = "Cache generation complete"
                        self._cache_jobs[job_id].result = _slim_cache_job_result(
                            result if isinstance(result, dict) else {}
                        )
                    block_results = (
                        result.get("blocks", {}).get("results", [])
                        if isinstance(result, dict)
                        else []
                    )
                    if isinstance(block_results, list) and block_results:
                        self.publish_latest_block_metrics(
                            [r for r in block_results if isinstance(r, dict)]
                        )
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
                    "running_for_s": round(max(0.0, time.monotonic() - job.started_at_monotonic), 1),
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
