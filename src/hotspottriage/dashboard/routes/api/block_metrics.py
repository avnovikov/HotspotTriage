"""Dashboard API: heatmap matrix, per-block narrative, and metric histograms."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from hotspottriage.dashboard.block_narrative_payload import build_block_narrative_payload
from hotspottriage.dashboard.distribution_histogram import DISTRIBUTION_METRICS, build_distribution_api_payload
from hotspottriage.dashboard.heatmap_matrix import HEATMAP_MAX_LIMIT, build_heatmap_api_payload


def register_block_metric_routes(router: APIRouter, dash: Any) -> None:
    """Register ``/stats/heatmap``, ``/stats/block_narrative``, ``/stats/distribution``."""

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
        return build_heatmap_api_payload(raw_rows, limit=limit)

    @router.get("/stats/block_narrative")
    def block_narrative(path: str = "") -> dict[str, Any]:
        """Lazy score narrative for one block path (heatmap row ``path``)."""
        raw_path = str(path).strip()
        if not raw_path:
            raise HTTPException(
                status_code=400,
                detail="path query parameter is required",
            )
        rows = dash.block_store.read_rows()
        cfg = dash._full_analyze_config_for_scoring()
        payload = build_block_narrative_payload(
            raw_path=raw_path, rows=rows, merged_config=cfg
        )
        if payload is not None:
            return payload
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
        return build_distribution_api_payload(rows, metric=name)
