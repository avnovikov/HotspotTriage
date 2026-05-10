"""FastAPI ``/api`` routes for the HotspotTriage dashboard."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from hotspottriage import cache as _cache
from hotspottriage import config as _config
from hotspottriage import explain as _explain_mod
from hotspottriage import score as _score_mod
from hotspottriage import stats as _stats_mod
from hotspottriage.discovery import is_git_url
from hotspottriage.dashboard.boundary import DashboardConfigPatchBody
from hotspottriage.dashboard.cache_http import (
    normalize_cache_target,
    parse_cache_filter_payload,
    validated_cache_request,
)
from hotspottriage.dashboard.cache_jobs import enqueue_cache_generation_job
from hotspottriage.dashboard.log_handler import MemoryLogHandler
from hotspottriage.dashboard.stats import StatsCollector
from hotspottriage.dashboard.stats_api import (
    DISTRIBUTION_METRICS,
    HEATMAP_MAX_LIMIT,
    HEATMAP_SCORE_COLUMNS,
    build_heatmap_rows,
    heatmap_column_maxima,
    histogram_buckets,
    sse_json_every,
)
from hotspottriage.username_privacy import redact_usernames_in_text


def build_dashboard_api_router(dash: Any) -> APIRouter:
    """Return an ``APIRouter`` with prefix ``/api`` wired to *dash* (:class:`DashboardServer`)."""
    router = APIRouter(prefix="/api")
    stats_ref: StatsCollector = dash._stats
    log_ref: MemoryLogHandler = dash._log_handler
    started = dash._started_at

    @router.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "alive",
            "uptime_s": round(time.monotonic() - started, 1),
        }

    @router.get("/config")
    def get_config() -> dict[str, Any]:
        return dash._enrich_config_snapshot_for_ui(dash._merged_snapshot())

    @router.post("/config/patch")
    def patch_config(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            body_model = DashboardConfigPatchBody.model_validate(
                payload if isinstance(payload, dict) else {}
            )
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=e.errors()) from e
        body = {k: v for k, v in body_model.model_dump(exclude_none=True).items()}
        if not body:
            raise HTTPException(
                status_code=400,
                detail="patch body must include metric_normalization and/or score_aggregation and/or proposed_models",
            )
        with dash._patch_lock:
            current = dash._load_patch_unlocked()
            merged_file = _config._deep_merge(current, body)
            try:
                dash._validate_merged_patch(merged_file)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            dash._write_patch_unlocked(merged_file)
        return {"status": "ok", "merged_keys": sorted(body.keys())}

    @router.get("/stats/heatmap")
    def stats_heatmap(limit: int = 500) -> dict[str, Any]:
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise HTTPException(
                status_code=400,
                detail="limit must be an integer",
            )
        if limit < 1:
            raise HTTPException(status_code=400, detail="limit must be >= 1")
        if limit > HEATMAP_MAX_LIMIT:
            raise HTTPException(
                status_code=400,
                detail=f"limit must be <= {HEATMAP_MAX_LIMIT}",
            )
        raw_rows = dash.block_store.read_rows()
        rows = build_heatmap_rows(raw_rows, limit=limit)
        column_maxima = heatmap_column_maxima(rows, columns=HEATMAP_SCORE_COLUMNS)
        return {
            "limit": limit,
            "columns": list(HEATMAP_SCORE_COLUMNS),
            "rows": rows,
            "column_maxima": column_maxima,
        }

    @router.get("/stats/block_narrative")
    def block_narrative(path: str = "") -> dict[str, Any]:
        """Lazy score narrative for one block path (heatmap row ``path``)."""
        raw_path = str(path).strip()
        if not raw_path:
            raise HTTPException(
                status_code=400,
                detail="path query parameter is required",
            )
        blob = dash.block_store.read_rows()
        for row in blob:
            if str(row.get("path", "")) == raw_path:
                stat = _stats_mod.statistic_from_complete_dict(row)
                cfg = dash._full_analyze_config_for_scoring()
                pm = cfg.get("proposed_models")
                rec: str | None = None
                if isinstance(pm, dict):
                    cand = pm.get(stat.score_band)
                    if isinstance(cand, str):
                        rec = cand
                fw_map = _score_mod.final_weight_multipliers_for_burdens(
                    cfg,
                    similarity_available=bool(cfg.get("similarity_enabled", True)),
                )
                if fw_map is not None and stat.score_subscores:
                    expl = _explain_mod.build_score_explanation(
                        stat, final_weights=fw_map
                    )
                    driver = _explain_mod.score_driver_from_subscores(
                        stat.score_subscores, final_weights=fw_map
                    )
                    narrative = _explain_mod.explain_score(
                        stat,
                        recommended_action=rec,
                        final_weights=fw_map,
                        contribution_detail="score_only",
                    )
                else:
                    expl = list(stat.score_explanation)
                    driver = stat.score_driver
                    narrative = _explain_mod.explain_score(
                        stat,
                        recommended_action=rec,
                        contribution_detail="score_only",
                    )
                return {
                    "path": raw_path,
                    "score_narrative": narrative,
                    "score_explanation": expl,
                    "score_driver": driver,
                }
        raise HTTPException(
            status_code=404,
            detail="path not found in loaded block metrics",
        )

    @router.get("/stats/distribution")
    def stats_distribution(metric: str = "") -> dict[str, Any]:
        name = str(metric).strip()
        if not name:
            return {"metric": "", "buckets": [], "counts": []}
        if name not in DISTRIBUTION_METRICS:
            return {"metric": name, "buckets": [], "counts": []}
        rows = dash.block_store.read_rows()
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
        buckets, counts = histogram_buckets(values)
        return {"metric": name, "buckets": buckets, "counts": counts}

    @router.get("/cache/context")
    def get_cache_context() -> dict[str, Any]:
        return dash._enrich_cache_context_for_response(dash._load_local_state())

    @router.post("/cache/context")
    def set_cache_context(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = validated_cache_request(payload if isinstance(payload, dict) else None)
        filt, inc, exc = parse_cache_filter_payload(body)
        try:
            norm_target = normalize_cache_target(body.get("target", ""))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        updates = {
            "last_target": norm_target,
            "last_filter": "" if filt is None else filt,
            "last_include": inc,
            "last_exclude": exc,
            "last_score_metrics": dash._score_metrics_csv_for_cache_jobs(),
        }
        merged = dash._save_local_state(updates)
        return dash._enrich_cache_context_for_response(merged)

    @router.post("/cache/status")
    def cache_status(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = validated_cache_request(payload if isinstance(payload, dict) else None)
        try:
            target = normalize_cache_target(body.get("target", ""))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        if not target:
            raise HTTPException(status_code=400, detail="target is required")
        if is_git_url(target):
            raise HTTPException(
                status_code=400,
                detail="Dashboard cache inspection requires a local repository checkout path.",
            )
        filt, inc, exc = parse_cache_filter_payload(body)
        filt_arg = None if filt is None else filt
        dash._persist_cache_analysis_prefs(
            target=target,
            filt=filt_arg,
            include=inc,
            exclude=exc,
        )
        repo = Path(target)
        cache_dir = _cache.cache_path_for(repo)
        cache_file = cache_dir / _cache._CACHE_FILE
        metadata = _cache.get_metadata(repo)
        exists = cache_file.exists()
        size = cache_file.stat().st_size if exists else 0
        entries = metadata.get("entry_count", 0) if isinstance(metadata, dict) else 0
        usable = dash._hydrate_block_metrics_when_missing(repo, cache_file_exists=exists)
        stale = exists and not usable
        target_s = str(repo)
        cache_dir_s = str(cache_dir)
        return {
            "target": target_s,
            "target_display": redact_usernames_in_text(target_s),
            "cache_dir": cache_dir_s,
            "cache_dir_display": redact_usernames_in_text(cache_dir_s),
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

    @router.post("/cache/generate")
    def generate_cache(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = validated_cache_request(payload if isinstance(payload, dict) else None)
        try:
            target = normalize_cache_target(body.get("target", ""))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        if not target:
            raise HTTPException(status_code=400, detail="target is required")
        filt, inc, exc = parse_cache_filter_payload(body)
        filt_arg = filt
        score = dash._score_metrics_csv_for_cache_jobs()
        dash._persist_cache_analysis_prefs(
            target=target,
            filt=filt_arg,
            include=inc,
            exclude=exc,
        )
        job_id = enqueue_cache_generation_job(
            dash,
            target=target,
            filt=filt_arg,
            score_metrics=score,
            jobs=dash._cache_jobs,
            jobs_lock=dash._cache_jobs_lock,
        )
        return {"job_id": job_id, "status": "running"}

    @router.get("/cache/jobs/{job_id}")
    def cache_job_status(job_id: str) -> dict[str, Any]:
        with dash._cache_jobs_lock:
            job = dash._cache_jobs.get(job_id)
            if job is None:
                raise HTTPException(status_code=404, detail="cache job not found")
            return {
                "job_id": job.job_id,
                "status": job.status,
                "progress": job.progress,
                "message": job.message,
                "running_for_s": round(
                    max(0.0, time.monotonic() - job.started_at_monotonic), 1
                ),
                "error": job.error,
                "result": job.result,
            }

    @router.get("/stats")
    def get_stats() -> dict[str, Any]:
        return stats_ref.get_snapshot()

    @router.post("/stats/clear")
    def clear_stats() -> dict[str, str]:
        stats_ref.clear()
        return {"status": "cleared"}

    @router.get("/logs")
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

    @router.get("/logs/stream")
    def log_stream() -> StreamingResponse:
        return StreamingResponse(_log_sse(), media_type="text/event-stream")

    @router.get("/stats/stream")
    def stats_stream() -> StreamingResponse:
        return StreamingResponse(
            sse_json_every(5.0, stats_ref.get_snapshot),
            media_type="text/event-stream",
        )

    return router
