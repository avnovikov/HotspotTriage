"""FastAPI dashboard server (daemon thread or ASGI test client)."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass
import html as _html
import json
import socket
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator, Callable

import uvicorn
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from hotspottriage import cache as _cache
from hotspottriage import config as _config
from hotspottriage import normalize as _normalize
from hotspottriage import score as _score_mod
from hotspottriage import stats as _stats_mod
from hotspottriage.dashboard.cache_filter_fields import (
    compose_filter_from_fields,
    split_filter_for_fields,
)
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

_DEFAULT_SCORE_METRICS = "churn_per_sloc,cyclomatic"


def _parse_cache_filter_payload(body: dict[str, Any] | None) -> tuple[str | None, str, str]:
    """Return ``(filter_for_pipeline, include_csv, exclude_csv)`` from a JSON body.

    New clients send ``include`` / ``exclude``; legacy bodies send a single
    ``filter`` string (comma-separated, ``!`` negates).
    """
    body = body if isinstance(body, dict) else {}
    if "include" in body or "exclude" in body:
        inc = str(body.get("include") or "").strip()
        exc = str(body.get("exclude") or "").strip()
        filt = compose_filter_from_fields(inc, exc)
        return filt, inc, exc
    filt_legacy = str(body.get("filter") or "").strip()
    if not filt_legacy:
        return None, "", ""
    inc_l, exc_l = split_filter_for_fields(filt_legacy)
    return filt_legacy, inc_l, exc_l


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


async def _sse_json_every(
    interval_s: float,
    build_payload: Callable[[], Any],
) -> AsyncGenerator[str, None]:
    """SSE stream: emit JSON snapshots on a fixed interval."""
    while True:
        yield "data: " + json.dumps(build_payload()) + "\n\n"
        await asyncio.sleep(interval_s)


def _scores_doc_html() -> str:
    """Return a lightweight HTML page for ``SCORES.md``."""
    repo_root = Path(__file__).resolve().parents[3]
    scores_path = repo_root / "SCORES.md"
    try:
        body = scores_path.read_text(encoding="utf-8")
    except OSError:
        body = "# SCORES.md not found\n\nUnable to locate the `SCORES.md` file."
    escaped = _html.escape(body)
    return (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'/>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'/>"
        "<title>HotspotTriage Scores</title>"
        "<style>"
        "body{margin:0;padding:1rem;font-family:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
        "background:#fcfcfa;color:#1f2937;}"
        "main{max-width:980px;margin:0 auto;}"
        "pre{white-space:pre-wrap;word-break:break-word;background:#fff;border:1px solid #d1d5db;"
        "border-radius:10px;padding:1rem;line-height:1.45;box-shadow:0 2px 10px rgba(15,23,42,.08);}"
        "</style></head><body><main><pre>"
        f"{escaped}"
        "</pre></main></body></html>"
    )


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

    def _ensure_snapshot_defaults(self) -> None:
        snap = self._base_snapshot
        if not isinstance(snap.get("metric_normalization"), dict):
            snap["metric_normalization"] = deepcopy(_config.DEFAULTS["metric_normalization"])
        if not isinstance(snap.get("score_aggregation"), dict):
            snap["score_aggregation"] = deepcopy(_config.DEFAULTS["score_aggregation"])

    def publish_latest_block_metrics(self, rows: list[dict[str, Any]]) -> None:
        """Replace stored raw block rows used by distribution histograms."""
        scored_rows = self._derive_block_rows(rows)
        with self._block_metrics_lock:
            self._block_metrics_rows = scored_rows

    def _derive_block_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Score raw block rows using the current dashboard config snapshot."""
        snapshot = self._merged_snapshot()
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
                        snapshot,
                        score_metrics=list(snapshot.get("score_metrics") or []),
                        smell_weight=float(snapshot.get("smell_weight", 0.0)),
                        similarity_enabled=bool(snapshot.get("similarity_enabled", True)),
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

    def _analysis_config_overrides(self) -> dict[str, Any]:
        """Return saved dashboard scoring config used when regenerating heatmap rows."""
        snapshot = self._merged_snapshot()
        overrides: dict[str, Any] = {}
        for key in ("metric_normalization", "score_aggregation"):
            value = snapshot.get(key)
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
                    self.publish_latest_block_metrics(live_rows)
                    has_rows = True
            except Exception:
                pass
        if cache_file_exists and not has_rows:
            loaded_rows = _cache.load_block_results(repo)
            if loaded_rows:
                self.publish_latest_block_metrics(loaded_rows)
                has_rows = True
        return has_rows

    def _make_cache_job_progress_callback(self, job_id: str):
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
            with self._cache_jobs_lock:
                job = self._cache_jobs.get(job_id)
                if job is None:
                    return
                job.message = msg
                job.progress = min(96, max(job.progress, pct))

        return _cache_progress

    def _run_cache_generation_job(
        self,
        job_id: str,
        *,
        target: str,
        filt: str | None,
        score_metrics: str,
        cache_generator_mod: Any,
    ) -> None:
        progress_cb = self._make_cache_job_progress_callback(job_id)
        try:
            with self._cache_jobs_lock:
                job = self._cache_jobs.get(job_id)
                if job is not None:
                    job.progress = 8
                    job.message = "Starting…"
            result = cache_generator_mod.generate_full_cache(
                target=target,
                filter=filt,
                score_metrics=score_metrics,
                verbose=False,
                progress_callback=progress_cb,
                config_overrides=self._analysis_config_overrides(),
            )
            with self._cache_jobs_lock:
                job = self._cache_jobs.get(job_id)
                if job is None:
                    return
                job.status = "done"
                job.progress = 100
                job.message = "Cache generation complete"
                job.result = _slim_cache_job_result(
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
                job = self._cache_jobs.get(job_id)
                if job is None:
                    return
                job.status = "error"
                job.progress = 100
                job.message = "Cache generation failed"
                job.error = str(e)

    def _enqueue_cache_generation_job(
        self,
        *,
        target: str,
        filt: str | None,
        score_metrics: str,
    ) -> str:
        # Local import avoids circular dependency with mcp_server consumers.
        from hotspottriage import cache_generator as _cache_generator

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

        def _thread_main() -> None:
            self._run_cache_generation_job(
                job_id,
                target=target,
                filt=filt,
                score_metrics=score_metrics,
                cache_generator_mod=_cache_generator,
            )

        threading.Thread(
            target=_thread_main,
            daemon=True,
            name=f"cache-job-{job_id[:8]}",
        ).start()
        return job_id

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

        _static_dir = Path(__file__).resolve().parent / "static"
        app.mount("/dashboard/static", StaticFiles(directory=str(_static_dir)), name="dashboard-static")

        from hotspottriage.dashboard.routes.pages import router as pages_router
        app.include_router(pages_router)

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
            allowed = {"metric_normalization", "score_aggregation", "proposed_models"}
            extra = set(body.keys()) - allowed
            if extra:
                raise HTTPException(
                    status_code=400,
                    detail=f"unsupported patch key(s): {sorted(extra)}",
                )
            if not body:
                raise HTTPException(
                    status_code=400,
                    detail="patch body must include metric_normalization and/or score_aggregation and/or proposed_models",
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
            filt, inc, exc = _parse_cache_filter_payload(body)
            updates = {
                "last_target": _normalize_cache_target(body.get("target", "")),
                "last_filter": "" if filt is None else filt,
                "last_include": inc,
                "last_exclude": exc,
                "last_score_metrics": self._score_metrics_csv_for_cache_jobs(),
            }
            return self._save_local_state(updates)

        @app.post("/api/cache/status")
        def cache_status(payload: dict[str, Any] | None = None) -> dict[str, Any]:
            body = payload or {}
            target = _normalize_cache_target(body.get("target", ""))
            if not target:
                raise HTTPException(status_code=400, detail="target is required")
            filt, inc, exc = _parse_cache_filter_payload(body)
            filt_arg = None if filt is None else filt
            dash_self._persist_cache_analysis_prefs(
                target=target,
                filt=filt_arg,
                include=inc,
                exclude=exc,
            )
            repo = Path(target).resolve()
            cache_dir = _cache.cache_path_for(repo)
            cache_file = cache_dir / _cache._CACHE_FILE
            metadata = _cache.get_metadata(repo)
            exists = cache_file.exists()
            size = cache_file.stat().st_size if exists else 0
            entries = metadata.get("entry_count", 0) if isinstance(metadata, dict) else 0
            usable = dash_self._hydrate_block_metrics_when_missing(
                repo, cache_file_exists=exists
            )
            stale = exists and not usable
            return {
                "target": str(repo),
                "cache_dir": str(cache_dir),
                "exists": exists,
                "usable": usable,
                "stale": stale,
                "message": (
                    "Cache file is stale or incompatible; regenerate cache."
                    if stale
                    else ""
                ),
                "entries": int(entries),
                "size_bytes": int(size),
                "metadata": metadata,
            }

        @app.post("/api/cache/generate")
        def generate_cache(payload: dict[str, Any] | None = None) -> dict[str, Any]:
            body = payload or {}
            target = _normalize_cache_target(body.get("target", ""))
            if not target:
                raise HTTPException(status_code=400, detail="target is required")
            filt, inc, exc = _parse_cache_filter_payload(body)
            filt_arg = filt
            score = dash_self._score_metrics_csv_for_cache_jobs()
            dash_self._persist_cache_analysis_prefs(
                target=target,
                filt=filt_arg,
                include=inc,
                exclude=exc,
            )
            job_id = dash_self._enqueue_cache_generation_job(
                target=target, filt=filt_arg, score_metrics=score
            )
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

        @app.get("/api/stats/stream")
        def stats_stream() -> StreamingResponse:
            return StreamingResponse(
                _sse_json_every(5.0, stats_ref.get_snapshot),
                media_type="text/event-stream",
            )

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
