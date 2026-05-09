"""Canonical score metric IDs and sort keys (config validation, CLI help).

Kept separate from :mod:`hotspottriage.stats` so :mod:`hotspottriage.config` can
validate ``score_metrics`` / ``sort`` without importing the full statistics
pipeline (breaks CodeQL-reported import cycles).
"""
from __future__ import annotations

from hotspottriage import complexity as _complexity

SCORE_METRICS: tuple[str, ...] = (
    *_complexity.METRICS,
    "churn",
    "churn_per_sloc",
    "decayed_churn",
    "decayed_churn_per_sloc",
    "smell_count",
    "smell_severity",
    "smell_burden",
    "similarity_score",
)

SORT_KEYS: tuple[str, ...] = ("score", "file")
