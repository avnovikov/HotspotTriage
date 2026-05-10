"""Reconstruct scored statistics from raw cache rows or full dict dumps."""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Iterable

from hotspottriage import explain as _explain
from hotspottriage.statistic_row import Statistic

from hotspottriage.stats.risk_application import apply_risk_scores
from hotspottriage.stats.scoring import product_score


# ── shared field extraction (DRY) ────────────────────────────────────

def _int_field(row: dict[str, Any], key: str, default: int = 0) -> int:
    return int(row.get(key, default))


def _float_field(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    return float(row.get(key, default))


def _base_fields_from_row(row: dict[str, Any]) -> dict[str, Any]:
    """Extract the metric fields common to every Statistic-from-dict path."""
    return {
        "path": str(row.get("path", "")),
        "sloc": _int_field(row, "sloc"),
        "normalized_sloc": _float_field(row, "normalized_sloc"),
        "cyclomatic": _int_field(row, "cyclomatic"),
        "halstead": _int_field(row, "halstead"),
        "maintainability": _int_field(row, "maintainability"),
        "churn": _int_field(row, "churn"),
        "churn_per_sloc": _float_field(row, "churn_per_sloc"),
        "decayed_churn": _float_field(row, "decayed_churn"),
        "decayed_churn_per_sloc": _float_field(row, "decayed_churn_per_sloc"),
        "smell_count": _int_field(row, "smell_count"),
        "smell_severity": _float_field(row, "smell_severity"),
        "smell_burden": _float_field(row, "smell_burden"),
        "smells": dict(row.get("smells") or {}),
        "similarity_score": _float_field(row, "similarity_score"),
        "similarity_band": str(row.get("similarity_band", "n/a")),
        "match_count": _int_field(row, "match_count"),
    }


def _scoring_metrics_from_base(base: dict[str, Any]) -> dict[str, float]:
    """Float-valued metric dict fed into ``product_score`` / ``apply_risk_scores``."""
    return {
        "normalized_sloc": float(base["normalized_sloc"]),
        "cyclomatic": float(base["cyclomatic"]),
        "halstead": float(base["halstead"]),
        "maintainability": float(base["maintainability"]),
        "churn": float(base["churn"]),
        "churn_per_sloc": float(base["churn_per_sloc"]),
        "decayed_churn": float(base["decayed_churn"]),
        "decayed_churn_per_sloc": float(base["decayed_churn_per_sloc"]),
        "smell_count": float(base["smell_count"]),
        "smell_severity": float(base["smell_severity"]),
        "smell_burden": float(base["smell_burden"]),
        "similarity_score": float(base["similarity_score"]),
    }


# ── score metadata parsers (SRP) ─────────────────────────────────────

def _parse_score_subscores(raw: Any) -> dict[str, float]:
    if isinstance(raw, dict):
        return {str(k): float(v) for k, v in raw.items()}
    return {}


def _parse_score_explanation(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return _explain.sanitize_score_explanation_entries(raw)
    return []


def _parse_final_weights(raw: Any) -> dict[str, float] | None:
    if isinstance(raw, dict) and raw:
        return {str(k): float(v) for k, v in raw.items()}
    return None


def _parse_norm_inputs(raw: Any) -> dict[str, dict[str, float]] | None:
    if not isinstance(raw, dict) or not raw:
        return None
    result: dict[str, dict[str, float]] = {}
    for burden_key, inner in raw.items():
        if isinstance(inner, dict):
            result[str(burden_key)] = {str(k): float(v) for k, v in inner.items()}
    return result or None


# ── public functions ──────────────────────────────────────────────────

def statistic_from_raw_block_row(
    row: dict[str, Any],
    score_metrics: Iterable[str],
    *,
    smell_weight: float = 0.0,
    merged_config: dict[str, Any] | None = None,
    similarity_enabled: bool = True,
) -> Statistic:
    """Derive a scored ``Statistic`` from one raw cached block row."""
    base = _base_fields_from_row(row)
    path = base["path"]

    if path.startswith("__"):
        return Statistic(
            **base,
            score=_float_field(row, "score"),
            score_band=str(row.get("score_band", "n/a")),
            score_subscores=_parse_score_subscores(row.get("score_subscores")),
            score_driver=str(row.get("score_driver", "")),
            score_explanation=_parse_score_explanation(row.get("score_explanation")),
        )

    metrics = _scoring_metrics_from_base(base)
    stat = Statistic(
        **base,
        score=product_score(metrics, score_metrics, smell_weight=smell_weight),
        score_driver="",
        score_explanation=[],
    )
    cfg = merged_config if merged_config is not None else {}
    scored = [stat]
    apply_risk_scores(scored, cfg, similarity_enabled)
    return scored[0]


def statistic_from_complete_dict(row: dict[str, Any]) -> Statistic:
    """Rebuild a scored :class:`Statistic` from :meth:`Statistic.as_dict` output."""
    base = _base_fields_from_row(row)
    # complete_dict smells are {str: int}; coerce from the generic dict above.
    base["smells"] = {str(k): int(v) for k, v in base["smells"].items()}

    subs = _parse_score_subscores(row.get("score_subscores"))
    expl = _parse_score_explanation(row.get("score_explanation"))
    sfw = _parse_final_weights(row.get("score_final_weights"))
    sni = _parse_norm_inputs(row.get("score_norm_inputs"))

    st = Statistic(
        **base,
        score=_float_field(row, "score"),
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
