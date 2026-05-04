"""Statistic dataclass + aggregation, sorting, limiting.

The `score` column is the product of a user-chosen subset of metrics
(`SCORE_METRICS`), so the same run can answer different questions
("which files are complex AND churned?", "which are just complex?",
"which are unmaintainable AND churned?", etc.).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import prod
from pathlib import Path, PurePosixPath
from typing import Iterable

from code_complexity_py import complexity as _complexity

# Every metric that can appear in the output and contribute to the score.
SCORE_METRICS: tuple[str, ...] = (*_complexity.METRICS, "churn")
DEFAULT_SCORE_METRICS: tuple[str, ...] = ("churn", "cyclomatic")


@dataclass(frozen=True)
class Statistic:
    path: str
    sloc: int
    cyclomatic: int
    halstead: int
    maintainability: int
    churn: int
    score: int

    def as_dict(self) -> dict:
        return asdict(self)


SORT_KEYS: tuple[str, ...] = ("score", "file")


def _score(metrics: dict[str, int], score_metrics: Iterable[str]) -> int:
    return prod(metrics[m] for m in score_metrics)


def build_stats(
    repo: Path,
    files: Iterable[str],
    churn: dict[str, int],
    score_metrics: Iterable[str],
) -> list[Statistic]:
    sm = list(score_metrics)
    out: list[Statistic] = []
    for rel in files:
        m = _complexity.compute_all(repo / rel)
        m["churn"] = churn.get(rel, 0)
        out.append(
            Statistic(
                path=rel,
                sloc=m["sloc"],
                cyclomatic=m["cyclomatic"],
                halstead=m["halstead"],
                maintainability=m["maintainability"],
                churn=m["churn"],
                score=_score(m, sm),
            )
        )
    return out


def _ancestors(path: str) -> list[str]:
    parts = PurePosixPath(path).parts[:-1]
    return ["/".join(parts[: i + 1]) for i in range(len(parts))]


def aggregate_by_directory(
    stats: list[Statistic], score_metrics: Iterable[str]
) -> list[Statistic]:
    """Sum every metric across descendant files of each ancestor directory,
    then recompute score as the product of the chosen metrics."""
    sm = list(score_metrics)
    sums: dict[str, dict[str, int]] = {}
    for s in stats:
        for d in _ancestors(s.path):
            entry = sums.setdefault(d, {m: 0 for m in SCORE_METRICS})
            entry["sloc"] += s.sloc
            entry["cyclomatic"] += s.cyclomatic
            entry["halstead"] += s.halstead
            entry["maintainability"] += s.maintainability
            entry["churn"] += s.churn
    return [
        Statistic(path=d, **m, score=_score(m, sm)) for d, m in sums.items()
    ]


def sort_and_limit(
    stats: list[Statistic],
    by: str = "score",
    limit: int | None = None,
) -> list[Statistic]:
    if by not in SORT_KEYS:
        raise ValueError(f"unknown sort key: {by!r} (valid: {SORT_KEYS})")
    if by == "file":
        ordered = sorted(stats, key=lambda s: s.path)
    else:
        ordered = sorted(stats, key=lambda s: s.score, reverse=True)
    if limit is not None and limit > 0:
        ordered = ordered[:limit]
    return ordered
