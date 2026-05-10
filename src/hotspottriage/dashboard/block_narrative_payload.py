"""Build JSON payload for ``GET /api/stats/block_narrative`` (lazy score narrative)."""
from __future__ import annotations

from typing import Any

from hotspottriage import explain as _explain_mod
from hotspottriage import score as _score_mod
from hotspottriage import stats as _stats_mod


def build_block_narrative_payload(
    *,
    raw_path: str,
    rows: list[dict[str, Any]],
    merged_config: dict[str, Any],
) -> dict[str, Any] | None:
    """Return narrative payload for *raw_path* if it exists in *rows*; else ``None``."""
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
