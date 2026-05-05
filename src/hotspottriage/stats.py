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
from statistics import mean, pstdev
from typing import Iterable

from hotspottriage import block_churn as _block_churn
from hotspottriage import blocks as _blocks
from hotspottriage import cache as _cache
from hotspottriage import complexity as _complexity

# Every metric that may appear in the output and contribute to the score.
# The default recipe lives in `config.DEFAULTS["score_metrics"]`; this module
# only owns the validation set so it stays close to the data definitions.
SCORE_METRICS: tuple[str, ...] = (*_complexity.METRICS, "churn", "churn_per_sloc")


@dataclass(frozen=True)
class Statistic:
    path: str
    sloc: int
    normalized_sloc: float
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


def _normalize_sloc(values: list[int]) -> list[float]:
    """Z-score normalization for block SLOC values.

    Uses population standard deviation because we normalize the whole in-memory
    set of computed blocks for this run.
    """
    if not values:
        return []
    mu = mean(values)
    sigma = pstdev(values)
    if sigma == 0:
        return [0.0] * len(values)
    return [(v - mu) / sigma for v in values]


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
                normalized_sloc=0.0,
                cyclomatic=int(m["cyclomatic"]),
                halstead=int(m["halstead"]),
                maintainability=int(m["maintainability"]),
                churn=int(m["churn"]),
                churn_per_sloc=m["churn_per_sloc"],
                score=_score(m, sm),
            )
        )
    return out


def build_block_stats(
    repo: Path,
    files: Iterable[str],
    score_metrics: Iterable[str],
    since: str | None = None,
    until: str | None = None,
    workers: int | None = None,
) -> list[Statistic]:
    """One Statistic per function/method (no class rows). Maintainability is
    inherited from the file. Churn is computed via `git log -L` per block,
    cached on disk by file blob SHA."""
    sm = list(score_metrics)
    files = list(files)

    blob_shas = _block_churn.file_blob_shas(repo)
    cache = _cache.Cache(repo)

    # Pass 1: extract blocks + compute file/snippet metrics.
    file_metrics: dict[str, dict[str, int]] = {}
    file_blocks: dict[str, list[_blocks.Block]] = {}
    file_sources: dict[str, str] = {}
    requests: list[tuple[str, str, int, int]] = []
    for rel in files:
        if rel not in blob_shas:
            continue
        try:
            src = (repo / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        file_sources[rel] = src
        file_metrics[rel] = _complexity.compute_all(repo / rel)
        bs = _blocks.extract_blocks(src)
        file_blocks[rel] = bs
        for b in bs:
            requests.append((rel, blob_shas[rel], b.start, b.end))

    # Pass 2: parallel git log -L for all blocks (cached).
    churns = _block_churn.compute_many(
        repo, requests, since, until, cache, workers=workers
    )
    cache.save()

    # Pass 3: assemble Statistic rows.
    rows: list[tuple[str, _blocks.Block, dict[str, float]]] = []
    for rel in files:
        if rel not in file_blocks:
            continue
        src = file_sources[rel]
        file_mi = file_metrics[rel]["maintainability"]
        for b in file_blocks[rel]:
            snippet = _complexity.slice_block(src, b.start, b.end)
            m: dict[str, float] = dict(_complexity.compute_for_source(snippet))
            m["maintainability"] = file_mi
            m["churn"] = churns.get((rel, b.start, b.end), 0)
            m["churn_per_sloc"] = _ratio(int(m["churn"]), int(m["sloc"]))
            rows.append((rel, b, m))

    normalized_slocs = _normalize_sloc([int(m["sloc"]) for _, _, m in rows])
    out: list[Statistic] = []
    for (rel, b, m), normalized_sloc in zip(rows, normalized_slocs):
        out.append(
                Statistic(
                    path=f"{rel}::{b.name}",
                    sloc=int(m["sloc"]),
                    normalized_sloc=normalized_sloc,
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
                normalized_sloc=0.0,
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
