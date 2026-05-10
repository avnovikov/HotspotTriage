"""File-level statistics: scoring helpers, build_stats, aggregation, sort.

Block pipeline lives in sibling modules (:mod:`hotspottriage.stats.pipeline`, etc.).
"""
from __future__ import annotations

from collections.abc import Callable
from math import prod
from pathlib import Path, PurePosixPath
from statistics import mean, pstdev
from typing import Any, Iterable

from hotspottriage import complexity as _complexity
from hotspottriage.config import DEFAULTS as _DEFAULTS
from hotspottriage.score_metrics import SORT_KEYS
from hotspottriage.statistic_row import Statistic

def block_similarity_kwargs_from_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """Keyword arguments for :func:`build_block_stats` DeepCSIM integration."""
    return {
        "similarity_enabled": bool(cfg.get("similarity_enabled", True)),
        "similarity_threshold": float(cfg.get("similarity_threshold", 80.0)),
        "similarity_band_high": float(cfg.get("similarity_band_high", 85.0)),
        "similarity_band_medium": float(cfg.get("similarity_band_medium", 70.0)),
        "similarity_band_low": float(cfg.get("similarity_band_low", 50.0)),
        "similarity_max_pairwise_blocks": int(
            cfg.get("similarity_max_pairwise_blocks", 2500)
        ),
        "similarity_aggregate_row": bool(cfg.get("similarity_aggregate_row", True)),
    }


def _ratio(churn: float | int, sloc: int, *, min_sloc_for_ratio: int) -> float:
    """Churn per SLOC with optional denominator floor (``min_sloc_for_ratio``).

    When ``sloc`` is positive, the divisor is ``max(sloc, min_sloc_for_ratio)`` so
    very small blocks do not explode ``churn / sloc``. ``sloc == 0`` yields ``0.0``.
    """
    s = int(sloc)
    if s <= 0:
        return 0.0
    denom = max(s, int(min_sloc_for_ratio))
    return float(churn) / float(denom)


def _score(
    metrics: dict[str, float], score_metrics: Iterable[str], *, smell_weight: float = 0.0
) -> float:
    factors: list[float] = []
    for metric in score_metrics:
        if metric == "smell_count":
            # Weighted so weight=0 is neutral (factor=1.0), preserving legacy scores.
            factors.append(1.0 + (smell_weight * metrics["smell_count"]))
        elif metric == "smell_severity":
            factors.append(1.0 + float(metrics.get("smell_severity", 0.0)))
        elif metric == "smell_burden":
            factors.append(1.0 + float(metrics.get("smell_burden", 0.0)))
        elif metric == "similarity_score":
            # Higher structural similarity increases score (optional metric).
            s = float(metrics.get("similarity_score", 0.0))
            factors.append(1.0 + s / 100.0)
        else:
            factors.append(metrics[metric])
    return float(prod(factors))


def _finalize_smell_burden(metrics_dicts: list[dict[str, Any]]) -> None:
    """Set ``smell_burden`` on each metrics dict using per-run count normalization.

    ``norm(smell_count)`` is ``count / max(1, max count in this batch)`` so values
    stay in ``[0, 1]`` within one analysis run. Formula::

        smell_burden = 0.5 * norm(smell_count) + 0.5 * smell_severity
    """
    if not metrics_dicts:
        return
    max_c = max(int(m["smell_count"]) for m in metrics_dicts)
    denom = max(1, max_c)
    for m in metrics_dicts:
        cnt = int(m["smell_count"])
        norm = cnt / denom
        sev = float(m.get("smell_severity", 0.0))
        m["smell_burden"] = 0.5 * norm + 0.5 * sev


def _normalize_sloc(values: list[int]) -> list[float]:
    """Z-score normalization for block SLOC values.

    Uses population standard deviation because we normalize the whole in-memory
    set of computed blocks for this run.
    """
    if not values:
        return []
    mu = mean(values)
    sigma = pstdev(values)
    if sigma == 0:
        return [0.0] * len(values)
    return [(v - mu) / sigma for v in values]


def _decayed_value(
    value: float,
    age_seconds: int,
    half_life_seconds: int,
) -> float:
    """Apply exponential decay to a value based on its age.
    
    Formula: decayed = value * (0.5) ^ (age_seconds / half_life_seconds)
    
    Args:
        value: Original value to decay
        age_seconds: Age in seconds (current_time - event_time)
        half_life_seconds: Half-life period in seconds
    
    Returns:
        Decayed value
    """
    if half_life_seconds <= 0 or age_seconds <= 0:
        return value
    decay_factor = 0.5 ** (age_seconds / half_life_seconds)
    return value * decay_factor


def build_stats(
    repo: Path,
    files: Iterable[str],
    churn: dict[str, int],
    score_metrics: Iterable[str],
    decay_half_life: int | None = None,
    smell_weight: float = 0.0,
    progress_callback: Callable[[str, int, int], None] | None = None,
    merged_config: dict[str, Any] | None = None,
) -> list[Statistic]:
    from hotspottriage import churn as _churn
    from hotspottriage import smell as _smell
    from datetime import datetime

    sm = list(score_metrics)
    files_list = list(files)
    total_files = len(files_list)
    if progress_callback:
        progress_callback("Analyzing files", 0, total_files)

    current_time = int(datetime.now().timestamp())
    timestamps = _churn.get_file_timestamps(repo, files_list)
    cfg = merged_config if merged_config is not None else _DEFAULTS
    min_sloc = int(cfg.get("min_sloc_for_ratio", _DEFAULTS["min_sloc_for_ratio"]))

    pending_metrics: list[dict[str, Any]] = []
    pending_meta: list[tuple[str, dict[str, int]]] = []
    for idx, rel in enumerate(files_list, start=1):
        raw_smells = _smell.compute_smells(repo / rel, merged_config)
        smell_summary = _smell.summarize_smells(raw_smells)
        m: dict[str, Any] = dict(_complexity.compute_all(repo / rel))
        m["churn"] = churn.get(rel, 0)
        m["churn_per_sloc"] = _ratio(int(m["churn"]), int(m["sloc"]), min_sloc_for_ratio=min_sloc)
        n_smells = len(raw_smells)
        m["smell_count"] = float(n_smells)
        m["smell_severity"] = (
            sum(float(x.get("severity", 0.0)) for x in raw_smells) / max(1, n_smells)
            if raw_smells
            else 0.0
        )

        age_seconds = current_time - timestamps.get(rel, current_time)
        m["decayed_churn"] = (
            _decayed_value(m["churn"], age_seconds, decay_half_life)
            if decay_half_life
            else m["churn"]
        )
        m["decayed_churn_per_sloc"] = _ratio(
            m["decayed_churn"], int(m["sloc"]), min_sloc_for_ratio=min_sloc
        )

        m["similarity_score"] = 0.0
        pending_metrics.append(m)
        pending_meta.append((rel, smell_summary))
        if progress_callback:
            progress_callback(rel, idx, total_files)

    _finalize_smell_burden(pending_metrics)

    out: list[Statistic] = []
    for (rel, smell_summary), m in zip(pending_meta, pending_metrics):
        out.append(
            Statistic(
                path=rel,
                sloc=int(m["sloc"]),
                normalized_sloc=0.0,
                cyclomatic=int(m["cyclomatic"]),
                halstead=int(m["halstead"]),
                maintainability=int(m["maintainability"]),
                churn=int(m["churn"]),
                churn_per_sloc=float(m["churn_per_sloc"]),
                decayed_churn=float(m["decayed_churn"]),
                decayed_churn_per_sloc=float(m["decayed_churn_per_sloc"]),
                smell_count=int(m["smell_count"]),
                smell_severity=float(m["smell_severity"]),
                smell_burden=float(m["smell_burden"]),
                smells=smell_summary,
                similarity_score=0.0,
                similarity_band="n/a",
                match_count=0,
                score=_score(m, sm, smell_weight=smell_weight),
            )
        )
    return out


def _similarity_aggregate_statistic(agg: dict[str, Any]) -> Statistic:
    """Synthetic row with repo-wide DeepCSIM summary (``path`` is reserved)."""
    total_b = int(agg.get("blocks_total") or 0)
    mean = float(agg.get("mean_similarity_score") or 0.0)
    usages = int(agg.get("total_match_usages") or 0)
    usable = int(agg.get("blocks_with_metrics") or 0)
    return Statistic(
        path="__aggregate_similarity__::repo",
        sloc=total_b,
        normalized_sloc=0.0,
        cyclomatic=usable,
        halstead=usages,
        maintainability=0,
        churn=0,
        churn_per_sloc=0.0,
        decayed_churn=0.0,
        decayed_churn_per_sloc=0.0,
        smell_count=0,
        smell_severity=0.0,
        smell_burden=0.0,
        smells={},
        similarity_score=mean,
        similarity_band="aggregate",
        match_count=usages,
        score=mean,
        score_band="aggregate",
        score_subscores={},
    )



def _ancestors(path: str) -> list[str]:
    parts = PurePosixPath(path).parts[:-1]
    return ["/".join(parts[: i + 1]) for i in range(len(parts))]


def aggregate_by_directory(
    stats: list[Statistic],
    score_metrics: Iterable[str],
    *,
    smell_weight: float = 0.0,
) -> list[Statistic]:
    """For each ancestor directory, sum every additive metric across descendants
    and recompute `churn_per_sloc` and `decayed_churn_per_sloc` from the *summed* 
    totals (not an average of per-file ratios), then recompute the score."""
    sm = list(score_metrics)
    sums: dict[str, dict[str, int | float]] = {}
    additive = (
        "sloc",
        "cyclomatic",
        "halstead",
        "maintainability",
        "churn",
        "decayed_churn",
        "smell_count",
    )

    def _empty_dir_entry() -> dict[str, int | float]:
        row = {k: 0 for k in additive}
        row["weighted_smell_sev"] = 0.0
        row["weighted_smell_bur"] = 0.0
        return row

    for s in stats:
        if s.path.startswith("__"):
            continue
        for d in _ancestors(s.path):
            entry = sums.setdefault(d, _empty_dir_entry())
            for k in additive:
                entry[k] += getattr(s, k)
            sc = int(s.smell_count)
            entry["weighted_smell_sev"] = float(entry["weighted_smell_sev"]) + (
                s.smell_severity * sc
            )
            entry["weighted_smell_bur"] = float(entry["weighted_smell_bur"]) + (
                s.smell_burden * sc
            )

    min_sloc = int(_DEFAULTS.get("min_sloc_for_ratio", 1))
    out: list[Statistic] = []
    for d, m in sums.items():
        cps = _ratio(m["churn"], m["sloc"], min_sloc_for_ratio=min_sloc)
        dcps = _ratio(m["decayed_churn"], m["sloc"], min_sloc_for_ratio=min_sloc)
        tot_smell = int(m["smell_count"])
        smell_sev = float(m["weighted_smell_sev"]) / max(1, tot_smell)
        smell_bur = float(m["weighted_smell_bur"]) / max(1, tot_smell)
        full: dict[str, float] = {
            "sloc": float(m["sloc"]),
            "cyclomatic": float(m["cyclomatic"]),
            "halstead": float(m["halstead"]),
            "maintainability": float(m["maintainability"]),
            "churn": float(m["churn"]),
            "decayed_churn": float(m["decayed_churn"]),
            "churn_per_sloc": cps,
            "decayed_churn_per_sloc": dcps,
            "smell_count": float(m["smell_count"]),
            "smell_severity": smell_sev,
            "smell_burden": smell_bur,
            "similarity_score": 0.0,
        }
        out.append(
            Statistic(
                path=d,
                sloc=int(m["sloc"]),
                normalized_sloc=0.0,
                cyclomatic=int(m["cyclomatic"]),
                halstead=int(m["halstead"]),
                maintainability=int(m["maintainability"]),
                churn=int(m["churn"]),
                churn_per_sloc=cps,
                decayed_churn=m["decayed_churn"],
                decayed_churn_per_sloc=dcps,
                smell_count=tot_smell,
                smell_severity=smell_sev,
                smell_burden=smell_bur,
                smells={},
                similarity_score=0.0,
                similarity_band="n/a",
                match_count=0,
                score=_score(full, sm, smell_weight=smell_weight),
            )
        )
    return out


def sort_and_limit(
    stats: list[Statistic],
    by: str = "score",
    limit: int | None = None,
) -> list[Statistic]:
    if by not in SORT_KEYS:
        raise ValueError(f"unknown sort key: {by!r} (valid: {SORT_KEYS})")
    meta = [s for s in stats if s.path.startswith("__")]
    normal = [s for s in stats if not s.path.startswith("__")]
    if by == "file":
        ordered = sorted(normal, key=lambda s: s.path)
    else:
        ordered = sorted(normal, key=lambda s: s.score, reverse=True)
    if limit is not None and limit > 0:
        ordered = ordered[:limit]
    return ordered + meta
