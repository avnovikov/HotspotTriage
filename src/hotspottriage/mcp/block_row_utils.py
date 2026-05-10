"""Block-row helpers for MCP analyze summaries, deltas, and dashboard publishing."""
from __future__ import annotations

import math
from typing import Any

from hotspottriage import stats


def block_statistic_file_segment(row: stats.Statistic) -> str:
    """Repo-relative file key for a block statistic (strip ``::symbol``)."""
    return str(row.path).split("::", 1)[0]


def is_synthetic_block_statistic(row: stats.Statistic) -> bool:
    """True when the row's file segment is a synthetic path (starts with ``__``)."""
    return block_statistic_file_segment(row).startswith("__")


def is_block_row_for_delta(row: stats.Statistic) -> bool:
    p = str(row.path)
    if "::" not in p:
        return False
    if is_synthetic_block_statistic(row):
        return False
    return str(row.score_band).lower() != "aggregate"


def metric_triplet(
    before: int | float | None, after: int | float | None
) -> dict[str, int | float | None]:
    if before is None and after is None:
        return {"before": None, "after": None, "delta": None}
    if before is None:
        return {"before": None, "after": after, "delta": None}
    if after is None:
        return {"before": before, "after": None, "delta": None}
    delta = after - before
    return {"before": before, "after": after, "delta": delta}


def rows_equal_raw(a: stats.Statistic, b: stats.Statistic) -> bool:
    for name in ("cyclomatic", "sloc", "halstead", "churn", "smell_count"):
        if getattr(a, name) != getattr(b, name):
            return False
    for name in ("churn_per_sloc", "decayed_churn", "decayed_churn_per_sloc"):
        if not math.isclose(
            float(getattr(a, name)),
            float(getattr(b, name)),
            rel_tol=0.0,
            abs_tol=1e-6,
        ):
            return False
    return True


def normal_block_stat_count(rows: list[stats.Statistic]) -> int:
    """Count non-synthetic block rows (exclude aggregate paths whose file starts with ``__``)."""
    return sum(1 for r in rows if not is_synthetic_block_statistic(r))


def non_synthetic_block_rows(rows: list[stats.Statistic]) -> list[stats.Statistic]:
    return [r for r in rows if not is_synthetic_block_statistic(r)]


def synthetic_block_row_dicts(rows: list[stats.Statistic]) -> list[dict[str, Any]]:
    """``as_dict()`` rows for synthetic block paths (similarity aggregate, etc.)."""
    return [r.as_dict() for r in rows if is_synthetic_block_statistic(r)]


def block_metric_row_repo_file(path: str) -> str:
    """Repo-relative file path for a block metric row (strip ``::symbol``)."""
    file_key = path.split("::", 1)[0] if "::" in path else path
    return file_key.replace("\\", "/")
