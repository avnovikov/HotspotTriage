"""Statistic dataclass + aggregation, sorting, limiting.

Every Statistic carries every metric so a single CSV/JSON dump can be re-sorted
later without rerunning. The `score` column is the product of a user-chosen
subset of metrics (`-s` on the CLI), so the same run can answer different
questions ("which files are unstable AND complex?", "which are just complex?").

`churn_per_sloc` is derived: `churn / sloc` — instability normalized by file
size, so a small, frequently-rewritten file outranks a big, rarely-touched one.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from math import prod
from pathlib import Path, PurePosixPath
from statistics import mean, pstdev
from typing import Any, Iterable

from hotspottriage import block_churn as _block_churn
from hotspottriage import block_similarity as _block_similarity
from hotspottriage import blocks as _blocks
from hotspottriage import cache as _cache
from hotspottriage import complexity as _complexity

# Every metric that may appear in the output and contribute to the score.
# The default recipe lives in `config.DEFAULTS["score_metrics"]`; this module
# only owns the validation set so it stays close to the data definitions.
SCORE_METRICS: tuple[str, ...] = (
    *_complexity.METRICS,
    "churn",
    "churn_per_sloc",
    "decayed_churn",
    "decayed_churn_per_sloc",
    "smell_count",
    # Block-only (similarity_* columns); only meaningful when ``granularity: block``.
    "similarity_score",
)


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
    decayed_churn: float
    decayed_churn_per_sloc: float
    smell_count: int
    smells: dict[str, int]
    similarity_score: float
    similarity_band: str
    match_count: int
    score: float

    def as_dict(self) -> dict:
        return asdict(self)


SORT_KEYS: tuple[str, ...] = ("score", "file")


def block_similarity_kwargs_from_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """Keyword arguments for :func:`build_block_stats` DeepCSIM integration."""
    return {
        "similarity_enabled": bool(cfg.get("similarity_enabled", True)),
        "similarity_threshold": float(cfg.get("similarity_threshold", 80.0)),
        "similarity_band_high": float(cfg.get("similarity_band_high", 85.0)),
        "similarity_band_medium": float(cfg.get("similarity_band_medium", 70.0)),
        "similarity_band_low": float(cfg.get("similarity_band_low", 50.0)),
        "similarity_max_pairwise_blocks": int(
            cfg.get("similarity_max_pairwise_blocks", 2500)
        ),
        "similarity_aggregate_row": bool(cfg.get("similarity_aggregate_row", True)),
    }


def _ratio(churn: int, sloc: int) -> float:
    return churn / sloc if sloc > 0 else 0.0


def _score(
    metrics: dict[str, float], score_metrics: Iterable[str], *, smell_weight: float = 0.0
) -> float:
    factors: list[float] = []
    for metric in score_metrics:
        if metric == "smell_count":
            # Weighted so weight=0 is neutral (factor=1.0), preserving legacy scores.
            factors.append(1.0 + (smell_weight * metrics["smell_count"]))
        elif metric == "similarity_score":
            # Higher structural similarity increases score (optional metric).
            s = float(metrics.get("similarity_score", 0.0))
            factors.append(1.0 + s / 100.0)
        else:
            factors.append(metrics[metric])
    return float(prod(factors))


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


def _decayed_value(
    value: float,
    age_seconds: int,
    half_life_seconds: int,
) -> float:
    """Apply exponential decay to a value based on its age.
    
    Formula: decayed = value * (0.5) ^ (age_seconds / half_life_seconds)
    
    Args:
        value: Original value to decay
        age_seconds: Age in seconds (current_time - event_time)
        half_life_seconds: Half-life period in seconds
    
    Returns:
        Decayed value
    """
    if half_life_seconds <= 0 or age_seconds <= 0:
        return value
    decay_factor = 0.5 ** (age_seconds / half_life_seconds)
    return value * decay_factor


def build_stats(
    repo: Path,
    files: Iterable[str],
    churn: dict[str, int],
    score_metrics: Iterable[str],
    decay_half_life: int | None = None,
    smell_weight: float = 0.0,
    progress_callback: Callable[[str, int, int], None] | None = None,
) -> list[Statistic]:
    from hotspottriage import churn as _churn
    from hotspottriage import smell as _smell
    from datetime import datetime
    
    sm = list(score_metrics)
    files_list = list(files)
    total_files = len(files_list)
    if progress_callback:
        progress_callback("Analyzing files", 0, total_files)
    
    current_time = int(datetime.now().timestamp())
    timestamps = _churn.get_file_timestamps(repo, files_list)
    
    out: list[Statistic] = []
    for idx, rel in enumerate(files_list, start=1):
        raw_smells = _smell.compute_smells(repo / rel)
        smell_summary = _smell.summarize_smells(raw_smells)
        m: dict[str, float] = dict(_complexity.compute_all(repo / rel))
        m["churn"] = churn.get(rel, 0)
        m["churn_per_sloc"] = _ratio(int(m["churn"]), int(m["sloc"]))
        m["smell_count"] = float(len(raw_smells))
        
        age_seconds = current_time - timestamps.get(rel, current_time)
        m["decayed_churn"] = (
            _decayed_value(m["churn"], age_seconds, decay_half_life)
            if decay_half_life
            else m["churn"]
        )
        m["decayed_churn_per_sloc"] = _ratio(
            int(m["decayed_churn"]), int(m["sloc"])
        )
        
        m["similarity_score"] = 0.0
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
                decayed_churn=m["decayed_churn"],
                decayed_churn_per_sloc=m["decayed_churn_per_sloc"],
                smell_count=int(m["smell_count"]),
                smells=smell_summary,
                similarity_score=0.0,
                similarity_band="n/a",
                match_count=0,
                score=_score(m, sm, smell_weight=smell_weight),
            )
        )
        if progress_callback:
            progress_callback(rel, idx, total_files)
    return out


def _similarity_aggregate_statistic(agg: dict[str, Any]) -> Statistic:
    """Synthetic row with repo-wide DeepCSIM summary (``path`` is reserved)."""
    total_b = int(agg.get("blocks_total") or 0)
    mean = float(agg.get("mean_similarity_score") or 0.0)
    usages = int(agg.get("total_match_usages") or 0)
    usable = int(agg.get("blocks_with_metrics") or 0)
    return Statistic(
        path="__aggregate_similarity__::repo",
        sloc=total_b,
        normalized_sloc=0.0,
        cyclomatic=usable,
        halstead=usages,
        maintainability=0,
        churn=0,
        churn_per_sloc=0.0,
        decayed_churn=0.0,
        decayed_churn_per_sloc=0.0,
        smell_count=0,
        smells={},
        similarity_score=mean,
        similarity_band="aggregate",
        match_count=usages,
        score=mean,
    )


def build_block_stats(
    repo: Path,
    files: Iterable[str],
    score_metrics: Iterable[str],
    since: str | None = None,
    until: str | None = None,
    workers: int | None = None,
    decay_half_life: int | None = None,
    smell_weight: float = 0.0,
    progress_callback: Callable[[str, int, int], None] | None = None,
    *,
    similarity_enabled: bool = True,
    similarity_threshold: float = 80.0,
    similarity_band_high: float = 85.0,
    similarity_band_medium: float = 70.0,
    similarity_band_low: float = 50.0,
    similarity_max_pairwise_blocks: int = 2500,
    similarity_aggregate_row: bool = True,
) -> list[Statistic]:
    """One Statistic per function/method (no class rows). Maintainability is
    inherited from the file. Churn is computed via `git log -L` per block,
    cached on disk by file blob SHA."""
    from hotspottriage import churn as _churn
    from hotspottriage import smell as _smell
    from datetime import datetime
    
    sm = list(score_metrics)
    files = list(files)
    blob_shas = _block_churn.file_blob_shas(repo)
    scan_total = sum(1 for f in files if f in blob_shas)
    scan_done = 0
    cache = _cache.Cache(repo)
    
    current_time = int(datetime.now().timestamp())
    timestamps = _churn.get_file_timestamps(repo, files)

    # Pass 1: extract blocks + compute file/snippet metrics.
    file_metrics: dict[str, dict[str, int]] = {}
    file_blocks: dict[str, list[_blocks.Block]] = {}
    file_sources: dict[str, str] = {}
    file_smells: dict[str, list[dict]] = {}
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
        file_smells[rel] = _smell.compute_smells(repo / rel)
        bs = _blocks.extract_blocks(src)
        file_blocks[rel] = bs
        for b in bs:
            requests.append((rel, blob_shas[rel], b.start, b.end))
        scan_done += 1
        if progress_callback:
            progress_callback(f"Scanning {rel}", scan_done, scan_total)

    # Pass 2: parallel git log -L for all blocks (cached).
    def _churn_progress(done: int, total: int) -> None:
        if progress_callback:
            progress_callback("Block churn (git log -L)", done, total)

    churns = _block_churn.compute_many(
        repo,
        requests,
        since,
        until,
        cache,
        workers=workers,
        on_progress=_churn_progress if progress_callback else None,
    )
    cache.save()

    # Pass 3: assemble Statistic rows.
    rows: list[tuple[str, _blocks.Block, dict[str, float]]] = []
    for rel in files:
        if rel not in file_blocks:
            continue
        src = file_sources[rel]
        file_mi = file_metrics[rel]["maintainability"]
        age_seconds = current_time - timestamps.get(rel, current_time)
        
        for b in file_blocks[rel]:
            snippet = _complexity.slice_block(src, b.start, b.end)
            m: dict[str, float] = dict(_complexity.compute_for_source(snippet))
            m["maintainability"] = file_mi
            m["churn"] = churns.get((rel, b.start, b.end), 0)
            m["churn_per_sloc"] = _ratio(int(m["churn"]), int(m["sloc"]))
            m["decayed_churn"] = (
                _decayed_value(m["churn"], age_seconds, decay_half_life)
                if decay_half_life
                else m["churn"]
            )
            m["decayed_churn_per_sloc"] = _ratio(
                int(m["decayed_churn"]), int(m["sloc"])
            )
            block_raw = [
                s
                for s in file_smells.get(rel, [])
                if _smell.finding_applies_to_block(s, b)
            ]
            block_summary = _smell.summarize_smells(block_raw)
            m["smell_count"] = float(len(block_raw))
            m["smells"] = block_summary
            rows.append((rel, b, m))

    sim_agg = _block_similarity.attach_similarity_to_rows(
        rows,
        file_sources,
        similarity_enabled=similarity_enabled,
        similarity_threshold=similarity_threshold,
        similarity_band_high=similarity_band_high,
        similarity_band_medium=similarity_band_medium,
        similarity_band_low=similarity_band_low,
        similarity_max_pairwise_blocks=similarity_max_pairwise_blocks,
    )

    normalized_slocs = _normalize_sloc([int(m["sloc"]) for _, _, m in rows])
    out: list[Statistic] = []
    total_rows = len(rows)
    if progress_callback:
        progress_callback("Building block rows", 0, total_rows)
    for i, ((rel, b, m), normalized_sloc) in enumerate(zip(rows, normalized_slocs), start=1):
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
                decayed_churn=m["decayed_churn"],
                decayed_churn_per_sloc=m["decayed_churn_per_sloc"],
                smell_count=int(m["smell_count"]),
                smells=m["smells"],
                similarity_score=float(m.get("similarity_score", 0.0)),
                similarity_band=str(m.get("similarity_band", "n/a")),
                match_count=int(m.get("match_count", 0)),
                score=_score(m, sm, smell_weight=smell_weight),
            )
        )
        if progress_callback:
            progress_callback(f"{rel}::{b.name}", i, total_rows)
    if (
        similarity_enabled
        and similarity_aggregate_row
        and sim_agg is not None
        and int(sim_agg.get("blocks_total") or 0) > 0
    ):
        out.append(_similarity_aggregate_statistic(sim_agg))
    return out


def _ancestors(path: str) -> list[str]:
    parts = PurePosixPath(path).parts[:-1]
    return ["/".join(parts[: i + 1]) for i in range(len(parts))]


def aggregate_by_directory(
    stats: list[Statistic],
    score_metrics: Iterable[str],
    *,
    smell_weight: float = 0.0,
) -> list[Statistic]:
    """For each ancestor directory, sum every additive metric across descendants
    and recompute `churn_per_sloc` and `decayed_churn_per_sloc` from the *summed* 
    totals (not an average of per-file ratios), then recompute the score."""
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
    for s in stats:
        if s.path.startswith("__"):
            continue
        for d in _ancestors(s.path):
            entry = sums.setdefault(d, {k: 0 for k in additive})
            for k in additive:
                entry[k] += getattr(s, k)

    out: list[Statistic] = []
    for d, m in sums.items():
        cps = _ratio(m["churn"], m["sloc"])
        dcps = _ratio(m["decayed_churn"], m["sloc"])
        full: dict[str, float] = {
            **m,
            "churn_per_sloc": cps,
            "decayed_churn_per_sloc": dcps,
            "smell_count": m["smell_count"],
            "similarity_score": 0.0,
        }
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
                decayed_churn=m["decayed_churn"],
                decayed_churn_per_sloc=dcps,
                smell_count=int(m["smell_count"]),
                smells={},
                similarity_score=0.0,
                similarity_band="n/a",
                match_count=0,
                score=_score(full, sm, smell_weight=smell_weight),
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
    meta = [s for s in stats if s.path.startswith("__")]
    normal = [s for s in stats if not s.path.startswith("__")]
    if by == "file":
        ordered = sorted(normal, key=lambda s: s.path)
    else:
        ordered = sorted(normal, key=lambda s: s.score, reverse=True)
    if limit is not None and limit > 0:
        ordered = ordered[:limit]
    return ordered + meta
