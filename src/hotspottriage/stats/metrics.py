"""Pure metric helpers: ratios, decay, SLOC normalization."""
from __future__ import annotations

from statistics import mean, pstdev


def ratio(churn: float | int, sloc: int, *, min_sloc_for_ratio: int) -> float:
    """Churn per SLOC with optional denominator floor (``min_sloc_for_ratio``).

    When ``sloc`` is positive, the divisor is ``max(sloc, min_sloc_for_ratio)``.
    ``sloc == 0`` yields ``0.0``.
    """
    s = int(sloc)
    if s <= 0:
        return 0.0
    denom = max(s, int(min_sloc_for_ratio))
    return float(churn) / float(denom)


def decayed_value(
    value: float,
    age_seconds: int,
    half_life_seconds: int,
) -> float:
    """Apply exponential decay: ``value * (0.5) ** (age_seconds / half_life_seconds)``."""
    if half_life_seconds <= 0 or age_seconds <= 0:
        return value
    decay_factor = 0.5 ** (age_seconds / half_life_seconds)
    return value * decay_factor


def normalize_sloc(values: list[int]) -> list[float]:
    """Z-score normalization for block SLOC values (population ``pstdev``)."""
    if not values:
        return []
    mu = mean(values)
    sigma = pstdev(values)
    if sigma == 0:
        return [0.0] * len(values)
    return [(v - mu) / sigma for v in values]
