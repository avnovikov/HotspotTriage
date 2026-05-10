"""Apply configured block risk / composite scores in-place."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from hotspottriage import explain as _explain
from hotspottriage import score as _risk_score
from hotspottriage.statistic_row import Statistic


def apply_risk_scores(
    out: list[Statistic], cfg: dict[str, Any], similarity_enabled: bool
) -> None:
    """Apply score aggregation in-place when enabled."""
    if not _risk_score.score_aggregation_enabled(cfg):
        return
    for idx, st in enumerate(out):
        if st.path.startswith("__"):
            continue
        rec = {
            "normalized_sloc": float(st.normalized_sloc),
            "cyclomatic": float(st.cyclomatic),
            "halstead": float(st.halstead),
            "maintainability": float(st.maintainability),
            "churn": float(st.churn),
            "churn_per_sloc": float(st.churn_per_sloc),
            "decayed_churn": float(st.decayed_churn),
            "decayed_churn_per_sloc": float(st.decayed_churn_per_sloc),
            "smell_count": float(st.smell_count),
            "smell_severity": float(st.smell_severity),
            "similarity_score": float(st.similarity_score),
            "match_count": float(st.match_count),
        }
        enriched = _risk_score.compute_score(rec, cfg, similarity_available=similarity_enabled)
        sub = dict(enriched["score_subscores"])
        fw_map = _risk_score.final_weight_multipliers_for_burdens(
            cfg, similarity_available=similarity_enabled
        )
        norm_inputs = _risk_score.normalized_block_inputs(
            rec, cfg, similarity_available=similarity_enabled
        )
        tmp = replace(
            st,
            score=float(enriched["score"]),
            score_band=str(enriched["score_band"]),
            score_subscores=sub,
            score_final_weights=fw_map,
            score_norm_inputs=norm_inputs,
        )
        explanation = _explain.build_score_explanation(tmp, final_weights=fw_map)
        driver = _explain.score_driver_from_subscores(sub, final_weights=fw_map)
        out[idx] = replace(
            tmp,
            score_driver=driver,
            score_explanation=explanation,
        )
