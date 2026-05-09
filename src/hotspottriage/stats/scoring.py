"""Deserialize cached block rows and apply aggregated risk scoring."""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Iterable

from hotspottriage import explain as _explain
from hotspottriage import score as _risk_score
from hotspottriage.statistic_row import Statistic

from hotspottriage.stats import core as _core

def _apply_risk_scores(
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



def statistic_from_raw_block_row(
    row: dict[str, Any],
    score_metrics: Iterable[str],
    *,
    smell_weight: float = 0.0,
    merged_config: dict[str, Any] | None = None,
    similarity_enabled: bool = True,
) -> Statistic:
    """Derive a scored ``Statistic`` from one raw cached block row."""
    path = str(row.get("path", ""))
    if path.startswith("__"):
        return Statistic(
            path=path,
            sloc=int(row.get("sloc", 0)),
            normalized_sloc=float(row.get("normalized_sloc", 0.0)),
            cyclomatic=int(row.get("cyclomatic", 0)),
            halstead=int(row.get("halstead", 0)),
            maintainability=int(row.get("maintainability", 0)),
            churn=int(row.get("churn", 0)),
            churn_per_sloc=float(row.get("churn_per_sloc", 0.0)),
            decayed_churn=float(row.get("decayed_churn", 0.0)),
            decayed_churn_per_sloc=float(row.get("decayed_churn_per_sloc", 0.0)),
            smell_count=int(row.get("smell_count", 0)),
            smell_severity=float(row.get("smell_severity", 0.0)),
            smell_burden=float(row.get("smell_burden", 0.0)),
            smells=dict(row.get("smells") or {}),
            similarity_score=float(row.get("similarity_score", 0.0)),
            similarity_band=str(row.get("similarity_band", "n/a")),
            match_count=int(row.get("match_count", 0)),
            score=float(row.get("score", 0.0)),
            score_band=str(row.get("score_band", "n/a")),
            score_subscores=dict(row.get("score_subscores") or {}),
            score_driver=str(row.get("score_driver", "")),
            score_explanation=_explain.sanitize_score_explanation_entries(
                row.get("score_explanation") or []
            ),
        )
    metrics = {
        "normalized_sloc": float(row.get("normalized_sloc", 0.0)),
        "cyclomatic": float(row.get("cyclomatic", 0.0)),
        "halstead": float(row.get("halstead", 0.0)),
        "maintainability": float(row.get("maintainability", 0.0)),
        "churn": float(row.get("churn", 0.0)),
        "churn_per_sloc": float(row.get("churn_per_sloc", 0.0)),
        "decayed_churn": float(row.get("decayed_churn", 0.0)),
        "decayed_churn_per_sloc": float(row.get("decayed_churn_per_sloc", 0.0)),
        "smell_count": float(row.get("smell_count", 0.0)),
        "smell_severity": float(row.get("smell_severity", 0.0)),
        "smell_burden": float(row.get("smell_burden", 0.0)),
        "similarity_score": float(row.get("similarity_score", 0.0)),
    }
    stat = Statistic(
        path=path,
        sloc=int(row.get("sloc", 0)),
        normalized_sloc=metrics["normalized_sloc"],
        cyclomatic=int(metrics["cyclomatic"]),
        halstead=int(metrics["halstead"]),
        maintainability=int(metrics["maintainability"]),
        churn=int(metrics["churn"]),
        churn_per_sloc=metrics["churn_per_sloc"],
        decayed_churn=metrics["decayed_churn"],
        decayed_churn_per_sloc=metrics["decayed_churn_per_sloc"],
        smell_count=int(metrics["smell_count"]),
        smell_severity=metrics["smell_severity"],
        smell_burden=metrics["smell_burden"],
        smells=dict(row.get("smells") or {}),
        similarity_score=metrics["similarity_score"],
        similarity_band=str(row.get("similarity_band", "n/a")),
        match_count=int(row.get("match_count", 0)),
        score=_core._score(metrics, score_metrics, smell_weight=smell_weight),
        score_driver="",
        score_explanation=[],
    )
    cfg = merged_config if merged_config is not None else {}
    scored = [stat]
    _apply_risk_scores(scored, cfg, similarity_enabled)
    return scored[0]


def statistic_from_complete_dict(row: dict[str, Any]) -> Statistic:
    """Rebuild a scored :class:`Statistic` from :meth:`Statistic.as_dict` output."""
    smells_raw = row.get("smells")
    smells: dict[str, Any] = dict(smells_raw) if isinstance(smells_raw, dict) else {}
    subs_raw = row.get("score_subscores")
    if isinstance(subs_raw, dict):
        subs = {str(k): float(v) for k, v in subs_raw.items()}
    else:
        subs = {}
    expl_raw = row.get("score_explanation")
    expl: list[dict[str, Any]] = (
        _explain.sanitize_score_explanation_entries(expl_raw)
        if isinstance(expl_raw, list)
        else []
    )
    sfw_raw = row.get("score_final_weights")
    sfw: dict[str, float] | None = None
    if isinstance(sfw_raw, dict) and sfw_raw:
        sfw = {str(k): float(v) for k, v in sfw_raw.items()}
    sni_raw = row.get("score_norm_inputs")
    sni: dict[str, dict[str, float]] | None = None
    if isinstance(sni_raw, dict) and sni_raw:
        sni = {}
        for bk, inner in sni_raw.items():
            if not isinstance(inner, dict):
                continue
            sni[str(bk)] = {str(k): float(v) for k, v in inner.items()}
    st = Statistic(
        path=str(row.get("path", "")),
        sloc=int(row.get("sloc", 0)),
        normalized_sloc=float(row.get("normalized_sloc", 0.0)),
        cyclomatic=int(row.get("cyclomatic", 0)),
        halstead=int(row.get("halstead", 0)),
        maintainability=int(row.get("maintainability", 0)),
        churn=int(row.get("churn", 0)),
        churn_per_sloc=float(row.get("churn_per_sloc", 0.0)),
        decayed_churn=float(row.get("decayed_churn", 0.0)),
        decayed_churn_per_sloc=float(row.get("decayed_churn_per_sloc", 0.0)),
        smell_count=int(row.get("smell_count", 0)),
        smell_severity=float(row.get("smell_severity", 0.0)),
        smell_burden=float(row.get("smell_burden", 0.0)),
        smells={str(k): int(v) for k, v in smells.items()},
        similarity_score=float(row.get("similarity_score", 0.0)),
        similarity_band=str(row.get("similarity_band", "n/a")),
        match_count=int(row.get("match_count", 0)),
        score=float(row.get("score", 0.0)),
        score_band=str(row.get("score_band", "n/a")),
        score_subscores=subs,
        score_driver=str(row.get("score_driver", "")),
        score_explanation=expl,
        score_final_weights=sfw,
        score_norm_inputs=sni,
    )
    if subs and not expl:
        st = replace(
            st,
            score_explanation=_explain.build_score_explanation(st, final_weights=sfw),
            score_driver=_explain.score_driver_from_subscores(subs, final_weights=sfw),
        )
    return st


def derive_block_statistics(
    rows: Iterable[dict[str, Any]],
    merged_config: dict[str, Any],
    *,
    score_metrics: Iterable[str] | None = None,
    smell_weight: float = 0.0,
    similarity_enabled: bool | None = None,
) -> list[Statistic]:
    """Derive scored block statistics from raw cached rows and active config."""
    cfg_score_metrics = (
        list(score_metrics)
        if score_metrics is not None
        else list(merged_config.get("score_metrics") or [])
    )
    sim_enabled = (
        bool(merged_config.get("similarity_enabled", True))
        if similarity_enabled is None
        else similarity_enabled
    )
    out: list[Statistic] = []
    for row in rows:
        if not isinstance(row, dict) or not str(row.get("path", "")).strip():
            continue
        out.append(
            statistic_from_raw_block_row(
                row,
                cfg_score_metrics,
                smell_weight=smell_weight,
                merged_config=merged_config,
                similarity_enabled=sim_enabled,
            )
        )
    return out


def derive_block_score_rows(
    rows: Iterable[dict[str, Any]],
    merged_config: dict[str, Any],
    *,
    score_metrics: Iterable[str] | None = None,
    smell_weight: float = 0.0,
    similarity_enabled: bool | None = None,
) -> list[dict[str, Any]]:
    """Return scored dict rows derived from raw cached rows."""
    return [
        stat.as_dict()
        for stat in derive_block_statistics(
            rows,
            merged_config,
            score_metrics=score_metrics,
            smell_weight=smell_weight,
            similarity_enabled=similarity_enabled,
        )
    ]
