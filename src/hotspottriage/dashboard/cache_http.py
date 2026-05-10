"""HTTP/cache request parsing and slim job payloads for the dashboard API."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError

from hotspottriage.dashboard.boundary import DashboardCacheRequestBody
from hotspottriage.dashboard.cache_filter_fields import (
    compose_filter_from_fields,
    split_filter_for_fields,
)
from hotspottriage.path_utils import normalize_user_target_string


def parse_cache_filter_payload(body: dict[str, Any] | None) -> tuple[str | None, str, str]:
    """Return ``(filter_for_pipeline, include_csv, exclude_csv)`` from a JSON body.

    New clients send ``include`` / ``exclude``; legacy bodies send a single
    ``filter`` string (comma-separated, ``!`` negates).

    Validated bodies may always include ``include`` / ``exclude`` keys (possibly
    empty); the legacy ``filter`` field is used only when both are blank.
    """
    body = body if isinstance(body, dict) else {}
    inc = str(body.get("include") or "").strip()
    exc = str(body.get("exclude") or "").strip()
    filt_legacy = str(body.get("filter") or "").strip()
    if inc or exc:
        filt = compose_filter_from_fields(inc, exc)
        return filt, inc, exc
    if not filt_legacy:
        return None, "", ""
    inc_l, exc_l = split_filter_for_fields(filt_legacy)
    return filt_legacy, inc_l, exc_l


def validated_cache_request(payload: dict[str, Any] | None) -> dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    try:
        return DashboardCacheRequestBody.model_validate(data).model_dump()
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors()) from e


def slim_cache_job_result(result: dict[str, Any]) -> dict[str, Any]:
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


def normalize_cache_target(raw_target: str) -> str:
    """Normalize cache target paths so ``./`` inputs persist as absolute paths."""
    return normalize_user_target_string(str(raw_target))


@dataclass
class CacheJob:
    job_id: str
    status: str
    progress: int
    message: str
    started_at_monotonic: float
    result: dict[str, Any] | None = None
    error: str | None = None
