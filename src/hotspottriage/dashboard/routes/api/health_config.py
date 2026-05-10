"""Dashboard API: health check and merged config + YAML patch."""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from hotspottriage import config as _config
from hotspottriage.dashboard.boundary import DashboardConfigPatchBody


def register_health_and_config_routes(router: APIRouter, dash: Any) -> None:
    """Register ``/health`` and ``/config`` routes on *router* (prefix ``/api`` on parent)."""

    @router.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "alive",
            "uptime_s": round(time.monotonic() - dash._started_at, 1),
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
