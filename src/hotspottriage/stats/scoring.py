"""File-level product score from ``score_metrics`` (CLI ``-s`` recipe)."""
from __future__ import annotations

from math import prod
from typing import Any, Iterable


def product_score(
    metrics: dict[str, float], score_metrics: Iterable[str], *, smell_weight: float = 0.0
) -> float:
    factors: list[float] = []
    for metric in score_metrics:
        if metric == "smell_count":
            factors.append(1.0 + (smell_weight * metrics["smell_count"]))
        elif metric == "smell_severity":
            factors.append(1.0 + float(metrics.get("smell_severity", 0.0)))
        elif metric == "smell_burden":
            factors.append(1.0 + float(metrics.get("smell_burden", 0.0)))
        elif metric == "similarity_score":
            s = float(metrics.get("similarity_score", 0.0))
            factors.append(1.0 + s / 100.0)
        else:
            factors.append(metrics[metric])
    return float(prod(factors))
