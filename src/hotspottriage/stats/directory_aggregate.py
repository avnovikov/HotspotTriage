"""Directory-level rolled-up statistics from file or block rows."""
from __future__ import annotations

from pathlib import PurePosixPath
from typing import Iterable

from hotspottriage.config import DEFAULTS
from hotspottriage.statistic_row import Statistic

from hotspottriage.stats.metrics import ratio
from hotspottriage.stats.scoring import product_score


def _ancestors(path: str) -> list[str]:
    parts = PurePosixPath(path).parts[:-1]
    return ["/".join(parts[: i + 1]) for i in range(len(parts))]


def aggregate_by_directory(
    stats: list[Statistic],
    score_metrics: Iterable[str],
    *,
    smell_weight: float = 0.0,
) -> list[Statistic]:
    """For each ancestor directory, sum additive metrics across descendants
    and recompute ``churn_per_sloc`` / ``decayed_churn_per_sloc`` from summed
    totals, then recompute the score.
    """
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

    min_sloc = int(DEFAULTS.get("min_sloc_for_ratio", 1))
    out: list[Statistic] = []
    for d, m in sums.items():
        cps = ratio(m["churn"], m["sloc"], min_sloc_for_ratio=min_sloc)
        dcps = ratio(m["decayed_churn"], m["sloc"], min_sloc_for_ratio=min_sloc)
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
                score=product_score(full, sm, smell_weight=smell_weight),
            )
        )
    return out
