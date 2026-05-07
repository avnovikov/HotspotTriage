"""Statistic dataclass + aggregation, sorting, limiting.

Every Statistic carries every metric so a single CSV/JSON dump can be re-sorted
later without rerunning. For **file** rows, ``score`` is the product of
``score_metrics`` (``-s`` on the CLI). For **block** rows, when
``score_aggregation.enabled`` is true (default), ``score`` is the configured
0–1 risk aggregate from :mod:`hotspottriage.score`; otherwise the product recipe
applies. ``score_band`` and ``score_subscores`` are set for block aggregated runs.

`churn_per_sloc` is derived: `churn / sloc` — instability normalized by file
size, so a small, frequently-rewritten file outranks a big, rarely-touched one.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from math import prod
from pathlib import Path, PurePosixPath
from statistics import mean, pstdev
from typing import Any, Iterable

from hotspottriage import block_churn as _block_churn
from hotspottriage import block_similarity as _block_similarity
from hotspottriage import blocks as _blocks
from hotspottriage import cache as _cache
from hotspottriage import complexity as _complexity
from hotspottriage import score as _risk_score

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
    "smell_severity",
    "smell_burden",
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
    smell_severity: float
    smell_burden: float
    smells: dict[str, int]
    similarity_score: float
    similarity_band: str
    match_count: int
    score: float
    score_band: str = "n/a"
    score_subscores: dict[str, float] = field(default_factory=dict)

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


def _ratio(churn: float | int, sloc: int) -> float:
    return float(churn) / sloc if sloc > 0 else 0.0


def _score(
    metrics: dict[str, float], score_metrics: Iterable[str], *, smell_weight: float = 0.0
) -> float:
    factors: list[float] = []
    for metric in score_metrics:
        if metric == "smell_count":
            # Weighted so weight=0 is neutral (factor=1.0), preserving legacy scores.
            factors.append(1.0 + (smell_weight * metrics["smell_count"]))
        elif metric == "smell_severity":
            factors.append(1.0 + float(metrics.get("smell_severity", 0.0)))
        elif metric == "smell_burden":
            factors.append(1.0 + float(metrics.get("smell_burden", 0.0)))
        elif metric == "similarity_score":
            # Higher structural similarity increases score (optional metric).
            s = float(metrics.get("similarity_score", 0.0))
            factors.append(1.0 + s / 100.0)
        else:
            factors.append(metrics[metric])
    return float(prod(factors))


def _finalize_smell_burden(metrics_dicts: list[dict[str, Any]]) -> None:
    """Set ``smell_burden`` on each metrics dict using per-run count normalization.

    ``norm(smell_count)`` is ``count / max(1, max count in this batch)`` so values
    stay in ``[0, 1]`` within one analysis run. Formula::

        smell_burden = 0.5 * norm(smell_count) + 0.5 * smell_severity
    """
    if not metrics_dicts:
        return
    max_c = max(int(m["smell_count"]) for m in metrics_dicts)
    denom = max(1, max_c)
    for m in metrics_dicts:
        cnt = int(m["smell_count"])
        norm = cnt / denom
        sev = float(m.get("smell_severity", 0.0))
        m["smell_burden"] = 0.5 * norm + 0.5 * sev


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
    merged_config: dict[str, Any] | None = None,
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

    pending_metrics: list[dict[str, Any]] = []
    pending_meta: list[tuple[str, dict[str, int]]] = []
    for idx, rel in enumerate(files_list, start=1):
        raw_smells = _smell.compute_smells(repo / rel, merged_config)
        smell_summary = _smell.summarize_smells(raw_smells)
        m: dict[str, Any] = dict(_complexity.compute_all(repo / rel))
        m["churn"] = churn.get(rel, 0)
        m["churn_per_sloc"] = _ratio(int(m["churn"]), int(m["sloc"]))
        n_smells = len(raw_smells)
        m["smell_count"] = float(n_smells)
        m["smell_severity"] = (
            sum(float(x.get("severity", 0.0)) for x in raw_smells) / max(1, n_smells)
            if raw_smells
            else 0.0
        )

        age_seconds = current_time - timestamps.get(rel, current_time)
        m["decayed_churn"] = (
            _decayed_value(m["churn"], age_seconds, decay_half_life)
            if decay_half_life
            else m["churn"]
        )
        m["decayed_churn_per_sloc"] = _ratio(m["decayed_churn"], int(m["sloc"]))

        m["similarity_score"] = 0.0
        pending_metrics.append(m)
        pending_meta.append((rel, smell_summary))
        if progress_callback:
            progress_callback(rel, idx, total_files)

    _finalize_smell_burden(pending_metrics)

    out: list[Statistic] = []
    for (rel, smell_summary), m in zip(pending_meta, pending_metrics):
        out.append(
            Statistic(
                path=rel,
                sloc=int(m["sloc"]),
                normalized_sloc=0.0,
                cyclomatic=int(m["cyclomatic"]),
                halstead=int(m["halstead"]),
                maintainability=int(m["maintainability"]),
                churn=int(m["churn"]),
                churn_per_sloc=float(m["churn_per_sloc"]),
                decayed_churn=float(m["decayed_churn"]),
                decayed_churn_per_sloc=float(m["decayed_churn_per_sloc"]),
                smell_count=int(m["smell_count"]),
                smell_severity=float(m["smell_severity"]),
                smell_burden=float(m["smell_burden"]),
                smells=smell_summary,
                similarity_score=0.0,
                similarity_band="n/a",
                match_count=0,
                score=_score(m, sm, smell_weight=smell_weight),
            )
        )
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
        smell_severity=0.0,
        smell_burden=0.0,
        smells={},
        similarity_score=mean,
        similarity_band="aggregate",
        match_count=usages,
        score=mean,
        score_band="aggregate",
        score_subscores={},
    )


@dataclass
class _BlockAnalysisContext:
    """Intermediate state for block-level analysis pipeline."""

    repo: Path
    files: list[str]
    blob_shas: dict[str, str]
    previous_rows: dict[str, dict[str, Any]]
    prev_rows_list: list[dict[str, Any]]
    timestamps: dict[str, int]
    current_time: int
    merged_config: dict[str, Any]


def _load_previous_cache(
    repo: Path, cache_manager: _cache.BlockCacheManager | None
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Load previous cache rows from manager or disk."""
    if cache_manager is not None:
        previous_rows = cache_manager.get_previous_rows_index()
        return previous_rows, list(previous_rows.values())
    prev_rows_list = _cache.load_block_results(repo) or []
    previous_rows = {
        r["path"]: r for r in prev_rows_list if isinstance(r, dict) and "path" in r
    }
    return previous_rows, prev_rows_list


def _scan_files_for_blocks(
    ctx: _BlockAnalysisContext,
    progress_callback: Callable[[str, int, int], None] | None,
) -> tuple[
    dict[str, dict[str, int]],
    dict[str, list[_blocks.Block]],
    dict[str, str],
    dict[str, list[dict[str, Any]]],
    list[tuple[str, str, int, int]],
]:
    """Pass 1: extract blocks + compute file/snippet metrics."""
    from hotspottriage import smell as _smell

    file_metrics: dict[str, dict[str, int]] = {}
    file_blocks: dict[str, list[_blocks.Block]] = {}
    file_sources: dict[str, str] = {}
    file_smells: dict[str, list[dict[str, Any]]] = {}
    requests: list[tuple[str, str, int, int]] = []

    scan_total = sum(1 for f in ctx.files if f in ctx.blob_shas)
    scan_done = 0
    if progress_callback and scan_total > 0:
        progress_callback("Scanning files", 0, scan_total)

    for rel in ctx.files:
        if rel not in ctx.blob_shas:
            continue
        if progress_callback:
            progress_callback(f"Scanning {rel}", scan_done, scan_total)
        try:
            src = (ctx.repo / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        file_sources[rel] = src
        file_metrics[rel] = _complexity.compute_all(ctx.repo / rel)
        file_smells[rel] = _smell.compute_smells(ctx.repo / rel, ctx.merged_config)
        bs = _blocks.extract_blocks(src)
        file_blocks[rel] = bs
        for b in bs:
            requests.append((rel, ctx.blob_shas[rel], b.start, b.end))
        scan_done += 1
        if progress_callback:
            progress_callback(f"Scanning {rel}", scan_done, scan_total)

    return file_metrics, file_blocks, file_sources, file_smells, requests


def _compute_block_churns(
    ctx: _BlockAnalysisContext,
    requests: list[tuple[str, str, int, int]],
    since: str | None,
    until: str | None,
    workers: int | None,
    progress_callback: Callable[[str, int, int], None] | None,
) -> dict[tuple[str, int, int], int]:
    """Pass 2: parallel git log -L for all blocks (cached)."""

    def _churn_progress(done: int, total: int) -> None:
        if progress_callback:
            progress_callback("Block churn (git log -L)", done, total)

    return _block_churn.compute_many(
        ctx.repo,
        requests,
        since,
        until,
        previous_rows=ctx.previous_rows,
        workers=workers,
        on_progress=_churn_progress if progress_callback else None,
    )


def _assemble_block_metrics(
    ctx: _BlockAnalysisContext,
    file_metrics: dict[str, dict[str, int]],
    file_blocks: dict[str, list[_blocks.Block]],
    file_sources: dict[str, str],
    file_smells: dict[str, list[dict[str, Any]]],
    churns: dict[tuple[str, int, int], int],
    decay_half_life: int | None,
) -> tuple[list[tuple[str, _blocks.Block, dict[str, Any]]], list[dict[str, str | int]]]:
    """Pass 3: assemble block metric dicts with cache metadata."""
    from hotspottriage import smell as _smell

    rows: list[tuple[str, _blocks.Block, dict[str, Any]]] = []
    row_cache_meta: list[dict[str, str | int]] = []

    for rel in ctx.files:
        if rel not in file_blocks:
            continue
        src = file_sources[rel]
        file_mi = file_metrics[rel]["maintainability"]
        age_seconds = ctx.current_time - ctx.timestamps.get(rel, ctx.current_time)

        for b in file_blocks[rel]:
            snippet = _complexity.slice_block(src, b.start, b.end)
            m: dict[str, Any] = dict(_complexity.compute_for_source(snippet))
            m["maintainability"] = file_mi
            m["churn"] = churns.get((rel, b.start, b.end), 0)
            m["churn_per_sloc"] = _ratio(int(m["churn"]), int(m["sloc"]))
            m["decayed_churn"] = (
                _decayed_value(m["churn"], age_seconds, decay_half_life)
                if decay_half_life
                else m["churn"]
            )
            m["decayed_churn_per_sloc"] = _ratio(m["decayed_churn"], int(m["sloc"]))

            block_raw = [
                s for s in file_smells.get(rel, []) if _smell.finding_applies_to_block(s, b)
            ]
            block_summary = _smell.summarize_smells(block_raw)
            n_blk = len(block_raw)
            m["smell_count"] = float(n_blk)
            m["smell_severity"] = (
                sum(float(s.get("severity", 0.0)) for s in block_raw) / max(1, n_blk)
                if block_raw
                else 0.0
            )
            m["smells"] = block_summary

            rows.append((rel, b, m))
            row_cache_meta.append({
                "_blob_sha": ctx.blob_shas[rel],
                "_start": b.start,
                "_end": b.end,
            })

    return rows, row_cache_meta


def _build_statistics(
    rows: list[tuple[str, _blocks.Block, dict[str, Any]]],
    score_metrics: list[str],
    smell_weight: float,
    progress_callback: Callable[[str, int, int], None] | None,
) -> list[Statistic]:
    """Convert block metric rows to Statistic objects."""
    normalized_slocs = _normalize_sloc([int(m["sloc"]) for _, _, m in rows])
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
                score=_score(m, score_metrics, smell_weight=smell_weight),
            )
        )
        if progress_callback:
            progress_callback(f"{rel}::{b.name}", i, total_rows)

    return out


def _apply_risk_scores(
    out: list[Statistic], cfg: dict[str, Any], similarity_enabled: bool
) -> None:
    """Apply score aggregation in-place when enabled."""
    if not _risk_score.score_aggregation_enabled(cfg):
        return
    for idx, st in enumerate(out):
        if st.path.startswith("__"):
            continue
        rec = {
            "normalized_sloc": float(st.normalized_sloc),
            "cyclomatic": float(st.cyclomatic),
            "halstead": float(st.halstead),
            "maintainability": float(st.maintainability),
            "churn": float(st.churn),
            "churn_per_sloc": float(st.churn_per_sloc),
            "decayed_churn": float(st.decayed_churn),
            "decayed_churn_per_sloc": float(st.decayed_churn_per_sloc),
            "smell_count": float(st.smell_count),
            "smell_severity": float(st.smell_severity),
            "similarity_score": float(st.similarity_score),
            "match_count": float(st.match_count),
        }
        enriched = _risk_score.compute_score(rec, cfg, similarity_available=similarity_enabled)
        out[idx] = replace(
            st,
            score=float(enriched["score"]),
            score_band=str(enriched["score_band"]),
            score_subscores=dict(enriched["score_subscores"]),
        )


def _persist_block_cache(
    out: list[Statistic],
    row_cache_meta: list[dict[str, str | int]],
    files: list[str],
    repo: Path,
    cache_manager: _cache.BlockCacheManager | None,
    prev_rows_list: list[dict[str, Any]],
) -> None:
    """Persist results with cache metadata for next run's churn lookup."""
    cache_rows: list[dict[str, Any]] = []
    for stat, meta in zip(out, row_cache_meta):
        d = stat.as_dict()
        d.update(meta)
        cache_rows.append(d)

    if not files:
        return

    targeted_files = set(files)
    if cache_manager is not None:
        cache_manager.put_rows(cache_rows, targeted_files=targeted_files)
    else:
        preserved: list[dict[str, Any]] = []
        for row in prev_rows_list:
            if not isinstance(row, dict):
                continue
            path = str(row.get("path", ""))
            if "::" not in path:
                continue
            rel, _ = path.split("::", 1)
            if rel not in targeted_files:
                preserved.append(row)
        _cache.save_block_results(repo, [*preserved, *cache_rows])


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
    merged_config: dict[str, Any] | None = None,
    *,
    cache_manager: _cache.BlockCacheManager | None = None,
    similarity_enabled: bool = True,
    similarity_threshold: float = 80.0,
    similarity_band_high: float = 85.0,
    similarity_band_medium: float = 70.0,
    similarity_band_low: float = 50.0,
    similarity_max_pairwise_blocks: int = 2500,
    similarity_aggregate_row: bool = True,
) -> list[Statistic]:
    """One Statistic per function/method (no class rows).

    Maintainability is inherited from the file. Churn is computed via
    `git log -L` per block, cached on disk by file blob SHA.
    """
    from hotspottriage import churn as _churn
    from datetime import datetime

    sm = list(score_metrics)
    files_list = list(files)
    cfg = merged_config if merged_config is not None else {}

    previous_rows, prev_rows_list = _load_previous_cache(repo, cache_manager)
    ctx = _BlockAnalysisContext(
        repo=repo,
        files=files_list,
        blob_shas=_block_churn.file_blob_shas(repo),
        previous_rows=previous_rows,
        prev_rows_list=prev_rows_list,
        timestamps=_churn.get_file_timestamps(repo, files_list),
        current_time=int(datetime.now().timestamp()),
        merged_config=cfg,
    )

    file_metrics, file_blocks, file_sources, file_smells, requests = _scan_files_for_blocks(
        ctx, progress_callback
    )
    churns = _compute_block_churns(ctx, requests, since, until, workers, progress_callback)
    rows, row_cache_meta = _assemble_block_metrics(
        ctx, file_metrics, file_blocks, file_sources, file_smells, churns, decay_half_life
    )

    _finalize_smell_burden([m for _, _, m in rows])

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

    out = _build_statistics(rows, sm, smell_weight, progress_callback)
    _apply_risk_scores(out, cfg, similarity_enabled)

    if (
        similarity_enabled
        and similarity_aggregate_row
        and sim_agg is not None
        and int(sim_agg.get("blocks_total") or 0) > 0
    ):
        out.append(_similarity_aggregate_statistic(sim_agg))

    try:
        _persist_block_cache(out, row_cache_meta, files_list, repo, cache_manager, prev_rows_list)
    except Exception:
        pass

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

    out: list[Statistic] = []
    for d, m in sums.items():
        cps = _ratio(m["churn"], m["sloc"])
        dcps = _ratio(m["decayed_churn"], m["sloc"])
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
