"""Build :class:`Statistic` rows from assembled block metric tuples."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from hotspottriage import blocks as _blocks
from hotspottriage.statistic_row import Statistic

from hotspottriage.stats.metrics import normalize_sloc
from hotspottriage.stats.scoring import product_score


def build_block_statistics_rows(
    rows: list[tuple[str, _blocks.Block, dict[str, Any]]],
    score_metrics: list[str],
    smell_weight: float,
    progress_callback: Callable[[str, int, int], None] | None,
) -> list[Statistic]:
    """Convert block metric rows to Statistic objects."""
    normalized_slocs = normalize_sloc([int(m["sloc"]) for _, _, m in rows])
    out: list[Statistic] = []
    total_rows = len(rows)
    if progress_callback:
        progress_callback("Building block rows", 0, total_rows)

    for i, ((rel, b, m), norm_sloc) in enumerate(zip(rows, normalized_slocs), start=1):
        out.append(
            Statistic(
                path=f"{rel}::{b.name}",
                sloc=int(m["sloc"]),
                normalized_sloc=norm_sloc,
                cyclomatic=int(m["cyclomatic"]),
                halstead=int(m["halstead"]),
                maintainability=int(m["maintainability"]),
                churn=int(m["churn"]),
                churn_per_sloc=m["churn_per_sloc"],
                decayed_churn=m["decayed_churn"],
                decayed_churn_per_sloc=m["decayed_churn_per_sloc"],
                smell_count=int(m["smell_count"]),
                smell_severity=float(m["smell_severity"]),
                smell_burden=float(m["smell_burden"]),
                smells=m["smells"],
                similarity_score=float(m.get("similarity_score", 0.0)),
                similarity_band=str(m.get("similarity_band", "n/a")),
                match_count=int(m.get("match_count", 0)),
                score=product_score(m, score_metrics, smell_weight=smell_weight),
            )
        )
        if progress_callback:
            progress_callback(f"{rel}::{b.name}", i, total_rows)

    return out
