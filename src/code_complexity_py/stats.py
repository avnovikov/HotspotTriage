"""Statistic dataclass + aggregation, sorting, limiting."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable

from code_complexity_py import complexity as _complexity


@dataclass(frozen=True)
class Statistic:
    path: str
    complexity: int
    churn: int

    @property
    def score(self) -> int:
        return self.complexity * self.churn

    def as_dict(self) -> dict:
        return {
            "path": self.path,
            "complexity": self.complexity,
            "churn": self.churn,
            "score": self.score,
        }


SortKey = str
SORT_KEYS: tuple[SortKey, ...] = ("score", "churn", "complexity", "file")


def build_stats(
    repo: Path,
    files: Iterable[str],
    churn: dict[str, int],
    strategy: str,
) -> list[Statistic]:
    out: list[Statistic] = []
    for rel in files:
        c = _complexity.compute(repo / rel, strategy)
        out.append(Statistic(path=rel, complexity=c, churn=churn.get(rel, 0)))
    return out


def _ancestors(path: str) -> list[str]:
    parts = PurePosixPath(path).parts[:-1]
    return ["/".join(parts[: i + 1]) for i in range(len(parts))]


def aggregate_by_directory(stats: list[Statistic]) -> list[Statistic]:
    """Sum complexity and churn for each ancestor directory of every path."""
    sums: dict[str, list[int]] = {}  # dir -> [complexity, churn]
    for s in stats:
        for d in _ancestors(s.path):
            entry = sums.setdefault(d, [0, 0])
            entry[0] += s.complexity
            entry[1] += s.churn
    return [Statistic(path=d, complexity=c, churn=ch) for d, (c, ch) in sums.items()]


def sort_and_limit(
    stats: list[Statistic],
    by: SortKey = "score",
    limit: int | None = None,
) -> list[Statistic]:
    if by not in SORT_KEYS:
        raise ValueError(f"unknown sort key: {by!r} (valid: {SORT_KEYS})")
    if by == "file":
        ordered = sorted(stats, key=lambda s: s.path)
    else:
        ordered = sorted(stats, key=lambda s: getattr(s, by), reverse=True)
    if limit is not None and limit > 0:
        ordered = ordered[:limit]
    return ordered
