"""Statistic dataclass + aggregation, sorting, limiting.

Every Statistic carries every metric so a single CSV/JSON dump can be re-sorted
later without rerunning. The `score` column is the product of a user-chosen
subset of metrics (`-s` on the CLI), so the same run can answer different
questions ("which files are unstable AND complex?", "which are just complex?").

`churn_per_sloc` is derived: `churn / sloc` — instability normalized by file
size, so a small, frequently-rewritten file outranks a big, rarely-touched one.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import prod
from pathlib import Path, PurePosixPath
from typing import Iterable

from code_complexity_py import complexity as _complexity

# Every metric that may appear in the output and contribute to the score.
SCORE_METRICS: tuple[str, ...] = (*_complexity.METRICS, "churn", "churn_per_sloc")
DEFAULT_SCORE_METRICS: tuple[str, ...] = ("churn_per_sloc", "cyclomatic")


@dataclass(frozen=True)
class Statistic:
    path: str
    sloc: int
    cyclomatic: int
    halstead: int
    maintainability: int
    churn: int
    churn_per_sloc: float
    score: float

    def as_dict(self) -> dict:
        return asdict(self)


SORT_KEYS: tuple[str, ...] = ("score", "file")


def _ratio(churn: int, sloc: int) -> float:
    return churn / sloc if sloc > 0 else 0.0


def _score(metrics: dict[str, float], score_metrics: Iterable[str]) -> float:
    return float(prod(metrics[m] for m in score_metrics))


def build_stats(
    repo: Path,
    files: Iterable[str],
    churn: dict[str, int],
    score_metrics: Iterable[str],
) -> list[Statistic]:
    sm = list(score_metrics)
    out: list[Statistic] = []
    for rel in files:
        m: dict[str, float] = dict(_complexity.compute_all(repo / rel))
        m["churn"] = churn.get(rel, 0)
        m["churn_per_sloc"] = _ratio(int(m["churn"]), int(m["sloc"]))
        out.append(
            Statistic(
                path=rel,
                sloc=int(m["sloc"]),
                cyclomatic=int(m["cyclomatic"]),
                halstead=int(m["halstead"]),
                maintainability=int(m["maintainability"]),
                churn=int(m["churn"]),
                churn_per_sloc=m["churn_per_sloc"],
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
    """For each ancestor directory, sum every additive metric across descendants
    and recompute `churn_per_sloc` from the *summed* totals (not an average of
    per-file ratios), then recompute the score."""
    sm = list(score_metrics)
    sums: dict[str, dict[str, int]] = {}
    additive = ("sloc", "cyclomatic", "halstead", "maintainability", "churn")
    for s in stats:
        for d in _ancestors(s.path):
            entry = sums.setdefault(d, {k: 0 for k in additive})
            for k in additive:
                entry[k] += getattr(s, k)

    out: list[Statistic] = []
    for d, m in sums.items():
        cps = _ratio(m["churn"], m["sloc"])
        full: dict[str, float] = {**m, "churn_per_sloc": cps}
        out.append(
            Statistic(
                path=d,
                sloc=m["sloc"],
                cyclomatic=m["cyclomatic"],
                halstead=m["halstead"],
                maintainability=m["maintainability"],
                churn=m["churn"],
                churn_per_sloc=cps,
                score=_score(full, sm),
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
    if by == "file":
        ordered = sorted(stats, key=lambda s: s.path)
    else:
        ordered = sorted(stats, key=lambda s: s.score, reverse=True)
    if limit is not None and limit > 0:
        ordered = ordered[:limit]
    return ordered
