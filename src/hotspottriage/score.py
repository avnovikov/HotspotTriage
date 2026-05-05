"""Configurable aggregated risk score (0–1, higher = worse) for block rows.

Combines normalized metric subscores with user-defined weights. Used when
``score_aggregation.enabled`` is true (default) for :func:`stats.build_block_stats`.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from hotspottriage.normalize import normalize

_FINAL_KEYS = (
    "complexity_burden",
    "churn_burden",
    "maintainability_burden",
    "smell_burden",
    "similarity_burden",
)


def effective_score_aggregation(merged_config: dict[str, Any]) -> dict[str, Any]:
    """Return ``score_aggregation`` with defaults from :data:`config.DEFAULTS` merged in."""
    from hotspottriage.config import DEFAULTS

    base: dict[str, Any] = deepcopy(DEFAULTS.get("score_aggregation") or {})
    user = merged_config.get("score_aggregation")
    if not isinstance(user, dict) or not user:
        return base
    for k, v in user.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            inner = dict(base[k])
            inner.update(v)
            base[k] = inner
        else:
            base[k] = deepcopy(v)
    return base


def score_aggregation_enabled(merged_config: dict[str, Any] | None) -> bool:
    if not merged_config:
        return True
    agg = merged_config.get("score_aggregation")
    if not isinstance(agg, dict):
        return True
    return bool(agg.get("enabled", True))


def _metric_norm(metric: str, value: float, merged_config: dict[str, Any]) -> float:
    mn = merged_config.get("metric_normalization") or {}
    sub = mn.get(metric)
    if not isinstance(sub, dict):
        return normalize(float(value), {"method": "identity"})
    return normalize(float(value), sub)


def _sum_weights(w: dict[str, Any]) -> float:
    total = 0.0
    for v in w.values():
        if isinstance(v, (int, float)):
            total += float(v)
    return total


def _normalized_weight_map(w: dict[str, Any], *, label: str) -> dict[str, float]:
    s = _sum_weights(w)
    if s <= 0:
        raise ValueError(f"{label} weights must sum to a positive number; got {w!r}")
    return {str(k): float(v) / s for k, v in w.items() if isinstance(v, (int, float))}


def _effective_final_weights(
    final_weights: dict[str, float],
    *,
    similarity_available: bool,
) -> dict[str, float]:
    """Return non-negative weights that sum to 1.

    When similarity is unavailable, ``similarity_burden`` is dropped from the
    map and remaining weights are scaled proportionally.
    """
    fw = {str(k): float(v) for k, v in final_weights.items()}
    for k in _FINAL_KEYS:
        if k not in fw:
            raise ValueError(f"score_aggregation.final_weights missing key {k!r}")
    if similarity_available:
        s = sum(fw.values())
        if s <= 0:
            raise ValueError("final_weights must sum to a positive number")
        return {k: fw[k] / s for k in _FINAL_KEYS}

    s_exc = sum(fw[k] for k in _FINAL_KEYS if k != "similarity_burden")
    if s_exc <= 0:
        raise ValueError(
            "when similarity is unavailable, final_weights must assign positive "
            "total weight to at least one burden other than similarity_burden"
        )
    return {k: fw[k] / s_exc for k in _FINAL_KEYS if k != "similarity_burden"}


def _classify_band(score: float, edges: list[float], names: list[str]) -> str:
    if len(edges) + 1 != len(names):
        raise ValueError(
            f"band_edges length must be len(band_names)-1; got edges={edges!r}, "
            f"names={names!r}"
        )
    x = float(score)
    for i, edge in enumerate(edges):
        if x < float(edge):
            return str(names[i])
    return str(names[-1])


def _record_float(record: dict[str, Any], key: str, default: float = 0.0) -> float:
    v = record.get(key, default)
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def compute_score(
    record: dict[str, Any],
    merged_config: dict[str, Any],
    *,
    similarity_available: bool = True,
) -> dict[str, Any]:
    """Augment ``record`` with ``score`` (0–1), ``score_band``, and ``score_subscores``.

    ``record`` must include the raw metrics used by ``metric_normalization`` and
    by the configured subscore weight maps. ``merged_config`` is the fully merged
    project config (including ``metric_normalization`` and ``score_aggregation``).

    When ``score_aggregation.enabled`` is false, returns ``record`` unchanged except
    ``score_band`` defaults to ``\"n/a\"`` and ``score_subscores`` to ``{}`` if absent.
    """
    out = dict(record)
    agg = effective_score_aggregation(merged_config)
    if not bool(agg.get("enabled", True)):
        out.setdefault("score_band", "n/a")
        out.setdefault("score_subscores", {})
        return out

    cw = _normalized_weight_map(agg.get("complexity_weights") or {}, label="complexity")
    chw = _normalized_weight_map(agg.get("churn_weights") or {}, label="churn")
    sw = _normalized_weight_map(agg.get("smell_weights") or {}, label="smell")
    siw = _normalized_weight_map(agg.get("similarity_weights") or {}, label="similarity")
    fw_raw = agg.get("final_weights") or {}
    if not isinstance(fw_raw, dict):
        raise ValueError("score_aggregation.final_weights must be a dict")
    fw = {str(k): float(v) for k, v in fw_raw.items() if isinstance(v, (int, float))}

    n_cyc = _metric_norm("cyclomatic", _record_float(record, "cyclomatic"), merged_config)
    n_hal = _metric_norm("halstead", _record_float(record, "halstead"), merged_config)
    n_nsloc = _metric_norm(
        "normalized_sloc", _record_float(record, "normalized_sloc"), merged_config
    )
    complexity_burden = (
        cw["cyclomatic"] * n_cyc + cw["halstead"] * n_hal + cw["normalized_sloc"] * n_nsloc
    )

    maintainability_burden = _metric_norm(
        "maintainability", _record_float(record, "maintainability"), merged_config
    )

    n_ch = _metric_norm("churn", _record_float(record, "churn"), merged_config)
    n_cps = _metric_norm("churn_per_sloc", _record_float(record, "churn_per_sloc"), merged_config)
    n_dch = _metric_norm("decayed_churn", _record_float(record, "decayed_churn"), merged_config)
    n_dcps = _metric_norm(
        "decayed_churn_per_sloc",
        _record_float(record, "decayed_churn_per_sloc"),
        merged_config,
    )
    churn_burden = (
        chw["churn"] * n_ch
        + chw["churn_per_sloc"] * n_cps
        + chw["decayed_churn"] * n_dch
        + chw["decayed_churn_per_sloc"] * n_dcps
    )

    n_smell_cnt = _metric_norm("smell_count", _record_float(record, "smell_count"), merged_config)
    smell_sev = _record_float(record, "smell_severity")
    smell_burden = sw["smell_count"] * n_smell_cnt + sw["smell_severity"] * smell_sev

    if similarity_available:
        n_sim = _metric_norm(
            "similarity_score", _record_float(record, "similarity_score"), merged_config
        )
        n_match = _metric_norm("match_count", _record_float(record, "match_count"), merged_config)
        similarity_burden = (
            siw["similarity_score"] * n_sim + siw["match_count"] * n_match
        )
    else:
        similarity_burden = 0.0

    burdens: dict[str, float] = {
        "complexity_burden": float(complexity_burden),
        "maintainability_burden": float(maintainability_burden),
        "churn_burden": float(churn_burden),
        "smell_burden": float(smell_burden),
        "similarity_burden": float(similarity_burden),
    }

    eff_fw = _effective_final_weights(fw, similarity_available=similarity_available)
    total = sum(eff_fw[k] * burdens[k] for k in eff_fw)
    score = max(0.0, min(1.0, float(total)))

    edges = agg.get("band_edges") or [0.30, 0.60, 0.80]
    names = agg.get("band_names") or ["low", "medium", "high", "critical"]
    if not isinstance(edges, list) or not all(isinstance(x, (int, float)) for x in edges):
        raise ValueError("score_aggregation.band_edges must be a list of numbers")
    if not isinstance(names, list) or not all(isinstance(x, str) for x in names):
        raise ValueError("score_aggregation.band_names must be a list of strings")
    edge_f = [float(x) for x in edges]
    for a, b in zip(edge_f, edge_f[1:]):
        if not (a < b):
            raise ValueError(
                f"score_aggregation.band_edges must be strictly increasing; got {edges!r}"
            )
    score_band = _classify_band(score, edge_f, [str(x) for x in names])

    out["score"] = score
    out["score_band"] = score_band
    out["score_subscores"] = burdens
    return out


def validate_score_aggregation(config: dict[str, Any]) -> None:
    """Validate ``score_aggregation``; no-op if disabled or missing."""
    agg = config.get("score_aggregation")
    if not isinstance(agg, dict) or not agg:
        return
    if not bool(agg.get("enabled", True)):
        return

    def _need_map(key: str) -> dict[str, Any]:
        m = agg.get(key)
        if not isinstance(m, dict) or not m:
            raise ValueError(f"score_aggregation.{key} must be a non-empty dict")
        return m

    _normalized_weight_map(_need_map("complexity_weights"), label="complexity_weights")
    _normalized_weight_map(_need_map("churn_weights"), label="churn_weights")
    _normalized_weight_map(_need_map("smell_weights"), label="smell_weights")
    _normalized_weight_map(_need_map("similarity_weights"), label="similarity_weights")

    fw = _need_map("final_weights")
    fw_f = {str(k): float(v) for k, v in fw.items() if isinstance(v, (int, float))}
    for k in _FINAL_KEYS:
        if k not in fw_f:
            raise ValueError(f"score_aggregation.final_weights missing {k!r}")
    s = sum(fw_f[k] for k in _FINAL_KEYS)
    if abs(s - 1.0) > 1e-5:
        raise ValueError(
            f"score_aggregation.final_weights must sum to 1.0; got {s} ({fw_f!r})"
        )

    edges = agg.get("band_edges", [0.30, 0.60, 0.80])
    names = agg.get("band_names", ["low", "medium", "high", "critical"])
    if not isinstance(edges, list) or len(edges) < 1:
        raise ValueError("score_aggregation.band_edges must be a non-empty list")
    if not isinstance(names, list) or len(names) != len(edges) + 1:
        raise ValueError(
            "score_aggregation.band_names must have length len(band_edges) + 1"
        )
    edge_f = [float(x) for x in edges]
    for a, b in zip(edge_f, edge_f[1:]):
        if not (a < b):
            raise ValueError(
                f"score_aggregation.band_edges must be strictly increasing; got {edges!r}"
            )
    for x in edge_f:
        if not (0.0 < x < 1.0):
            raise ValueError(
                f"each score_aggregation.band_edges value must be in (0, 1); got {x}"
            )

    # Smoke-run on neutral metrics using merged metric_normalization.
    neutral = {
        "normalized_sloc": 0.0,
        "cyclomatic": 1,
        "halstead": 20,
        "maintainability": 85,
        "churn": 0,
        "churn_per_sloc": 0.0,
        "decayed_churn": 0.0,
        "decayed_churn_per_sloc": 0.0,
        "smell_count": 0.0,
        "smell_severity": 0.0,
        "similarity_score": 0.0,
        "match_count": 0.0,
    }
    compute_score(neutral, config, similarity_available=True)
    compute_score(neutral, config, similarity_available=False)
