"""Sort and optionally truncate statistic rows."""
from __future__ import annotations

from hotspottriage.score_metrics import SORT_KEYS
from hotspottriage.statistic_row import Statistic


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
