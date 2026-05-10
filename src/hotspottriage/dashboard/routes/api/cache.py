"""Dashboard API: persisted cache UI context, disk cache status, and background jobs."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from hotspottriage import cache as _cache
from hotspottriage.discovery import is_git_url
from hotspottriage.dashboard.cache_http import (
    normalize_cache_target,
    parse_cache_filter_payload,
    validated_cache_request,
)
from hotspottriage.dashboard.cache_jobs import enqueue_cache_generation_job
from hotspottriage.username_privacy import redact_usernames_in_text


def _cache_status_payload(
    *,
    repo: Path,
    exists: bool,
    usable: bool,
    metadata: object,
) -> dict[str, Any]:
    """JSON body for ``POST /api/cache/status``."""
    cache_dir = _cache.cache_path_for(repo)
    cache_file = cache_dir / _cache._CACHE_FILE
    size = cache_file.stat().st_size if exists else 0
    entries = metadata.get("entry_count", 0) if isinstance(metadata, dict) else 0
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


def register_cache_routes(router: APIRouter, dash: Any) -> None:
    """Register ``/cache/context``, ``/cache/status``, ``/cache/generate``, ``/cache/jobs/{id}``."""

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
        usable = dash._hydrate_block_metrics_when_missing(repo, cache_file_exists=exists)
        return _cache_status_payload(
            repo=repo,
            exists=exists,
            usable=usable,
            metadata=metadata,
        )

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
