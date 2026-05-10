"""API metric histograms for ``/api/stats/distribution``."""
from __future__ import annotations

from typing import Any

# Numeric Statistic fields eligible for /api/stats/distribution histograms.
DISTRIBUTION_METRICS: frozenset[str] = frozenset(
    {
        "sloc",
        "normalized_sloc",
        "cyclomatic",
        "halstead",
        "maintainability",
        "churn",
        "churn_per_sloc",
        "decayed_churn",
        "decayed_churn_per_sloc",
        "smell_count",
        "smell_severity",
        "smell_burden",
        "similarity_score",
        "match_count",
        "score",
    }
)


def collect_numeric_metric_values(
    rows: list[dict[str, Any]], *, metric: str
) -> list[float]:
    """Collect *metric* values from block dict rows (skips bad rows / missing keys)."""
    values: list[float] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw = row.get(metric)
        if raw is None:
            continue
        try:
            values.append(float(raw))
        except (TypeError, ValueError):
            continue
    return values


def histogram_buckets(
    values: list[float], *, bins: int = 20
) -> tuple[list[list[float]], list[int]]:
    """Return ``buckets`` as ``[low, high]`` pairs and ``counts`` (same length)."""
    if not values:
        return [], []
    if bins < 1:
        raise ValueError("bins must be positive")
    vmin = float(min(values))
    vmax = float(max(values))
    if vmin == vmax:
        return [[vmin, vmax]], [len(values)]
    width = (vmax - vmin) / bins
    counts = [0] * bins
    buckets: list[list[float]] = []
    for i in range(bins):
        lo = vmin + i * width
        hi = vmin + (i + 1) * width
        if i == bins - 1:
            hi = vmax
        buckets.append([lo, hi])
    for v in values:
        fv = float(v)
        if fv >= vmax:
            idx = bins - 1
        elif fv <= vmin:
            idx = 0
        else:
            idx = int((fv - vmin) / width)
            if idx >= bins:
                idx = bins - 1
        counts[idx] += 1
    return buckets, counts


def build_distribution_api_payload(
    rows: list[dict[str, Any]], *, metric: str
) -> dict[str, Any]:
    """JSON body for ``GET /api/stats/distribution`` for a non-empty *metric* in ``DISTRIBUTION_METRICS``."""
    values = collect_numeric_metric_values(rows, metric=metric)
    if not values:
        return {"metric": metric, "buckets": [], "counts": []}
    buckets, counts = histogram_buckets(values)
    return {"metric": metric, "buckets": buckets, "counts": counts}
