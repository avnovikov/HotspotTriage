"""Dashboard API: heatmap matrix, per-block narrative, and metric histograms."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from hotspottriage import explain as _explain_mod
from hotspottriage import score as _score_mod
from hotspottriage import stats as _stats_mod
from hotspottriage.dashboard.stats_api import (
    DISTRIBUTION_METRICS,
    HEATMAP_MAX_LIMIT,
    HEATMAP_SCORE_COLUMNS,
    build_heatmap_rows,
    heatmap_column_maxima,
    histogram_buckets,
)


def _narrative_payload_for_path(
    *,
    raw_path: str,
    rows: list[dict[str, Any]],
    merged_config: dict[str, Any],
) -> dict[str, Any] | None:
    """Build ``block_narrative`` JSON for *raw_path* if it exists in *rows*."""
    for row in rows:
        if str(row.get("path", "")) != raw_path:
            continue
        stat = _stats_mod.statistic_from_complete_dict(row)
        pm = merged_config.get("proposed_models")
        recommended: str | None = None
        if isinstance(pm, dict):
            cand = pm.get(stat.score_band)
            if isinstance(cand, str):
                recommended = cand
        fw_map = _score_mod.final_weight_multipliers_for_burdens(
            merged_config,
            similarity_available=bool(merged_config.get("similarity_enabled", True)),
        )
        if fw_map is not None and stat.score_subscores:
            expl = _explain_mod.build_score_explanation(stat, final_weights=fw_map)
            driver = _explain_mod.score_driver_from_subscores(
                stat.score_subscores, final_weights=fw_map
            )
            narrative = _explain_mod.explain_score(
                stat,
                recommended_action=recommended,
                final_weights=fw_map,
                contribution_detail="score_only",
            )
        else:
            expl = list(stat.score_explanation)
            driver = stat.score_driver
            narrative = _explain_mod.explain_score(
                stat,
                recommended_action=recommended,
                contribution_detail="score_only",
            )
        return {
            "path": raw_path,
            "score_narrative": narrative,
            "score_explanation": expl,
            "score_driver": driver,
        }
    return None


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
        rows = dash.block_store.read_rows()
        cfg = dash._full_analyze_config_for_scoring()
        payload = _narrative_payload_for_path(raw_path=raw_path, rows=rows, merged_config=cfg)
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
