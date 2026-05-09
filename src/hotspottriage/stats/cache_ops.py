"""Block cache partition, merge, persistence, and raw row helpers."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from hotspottriage import blocks as _blocks
from hotspottriage import cache as _cache
from hotspottriage.statistic_row import Statistic

from hotspottriage.stats._constants import BLOCK_CACHE_META_KEYS, DERIVED_BLOCK_CACHE_KEYS


def _partition_complete_block_cache_files(
    files_list: list[str],
    blob_shas: dict[str, str],
    previous_rows: dict[str, dict[str, Any]],
    repo: Path,
) -> tuple[list[str], dict[str, str]]:
    """Split paths into cache-complete vs stale using HEAD blob and span coverage.

    A file is cache-complete when every AST block at HEAD has a cache row with
    matching ``(_start, _end)``, ``_blob_sha`` equal to the file blob at HEAD,
    and the row count matches the block count.
    """
    rows_by_file: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path_key, row in previous_rows.items():
        if not isinstance(row, dict):
            continue
        pk = str(path_key)
        if "::" not in pk:
            continue
        rel, _ = pk.split("::", 1)
        rows_by_file[rel].append(row)

    file_sources: dict[str, str] = {}
    for rel in files_list:
        if rel not in blob_shas:
            continue
        try:
            file_sources[rel] = (repo / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

    cached: list[str] = []
    for rel in files_list:
        if rel not in blob_shas or rel not in file_sources:
            continue
        blocks = _blocks.extract_blocks(file_sources[rel])
        current_blob = blob_shas[rel]
        rows = rows_by_file.get(rel, [])
        if len(rows) != len(blocks):
            continue
        by_span: dict[tuple[int, int], dict[str, Any]] = {}
        span_ok = True
        for row in rows:
            try:
                st = int(row["_start"])
                en = int(row["_end"])
            except (KeyError, TypeError, ValueError):
                span_ok = False
                break
            by_span[(st, en)] = row
        if not span_ok or len(by_span) != len(rows):
            continue
        coverage_ok = True
        for b in blocks:
            row = by_span.get((b.start, b.end))
            if row is None or str(row.get("_blob_sha", "")) != current_blob:
                coverage_ok = False
                break
        if coverage_ok:
            cached.append(rel)

    return cached, file_sources


def _metrics_dict_from_cached_row(row: dict[str, Any]) -> dict[str, Any]:
    """Metric dict for pipeline stages; strip cache metadata and reset similarity."""
    m = {
        k: v
        for k, v in row.items()
        if k not in BLOCK_CACHE_META_KEYS and k != "path"
    }
    m["similarity_score"] = 0.0
    m["similarity_band"] = "off"
    m["match_count"] = 0.0
    return m


def _cached_block_rows_tagged(
    files_list: list[str],
    cached_set: set[str],
    file_sources: dict[str, str],
    previous_rows: dict[str, dict[str, Any]],
) -> list[tuple[str, _blocks.Block, dict[str, Any], None]]:
    """Rebuild tagged rows from disk cache for files with unchanged blobs."""
    out: list[tuple[str, _blocks.Block, dict[str, Any], None]] = []
    for rel in files_list:
        if rel not in cached_set:
            continue
        src = file_sources[rel]
        for b in _blocks.extract_blocks(src):
            path_key = f"{rel}::{b.name}"
            row = previous_rows[path_key]
            m = _metrics_dict_from_cached_row(row)
            out.append((rel, b, m, None))
    return out


def _merge_tagged_block_rows_by_file_order(
    files_list: list[str],
    cached_set: set[str],
    cached_rows: list[tuple[str, _blocks.Block, dict[str, Any], None]],
    stale_tagged: list[tuple[str, _blocks.Block, dict[str, Any], dict[str, str | int]]],
) -> list[tuple[str, _blocks.Block, dict[str, Any], dict[str, str | int] | None]]:
    stale_by_file: dict[str, list[tuple[str, _blocks.Block, dict[str, Any], dict[str, str | int]]]] = (
        defaultdict(list)
    )
    for item in stale_tagged:
        stale_by_file[item[0]].append(item)
    cached_by_file: dict[str, list[tuple[str, _blocks.Block, dict[str, Any], None]]] = defaultdict(
        list
    )
    for item in cached_rows:
        cached_by_file[item[0]].append(item)

    merged: list[
        tuple[str, _blocks.Block, dict[str, Any], dict[str, str | int] | None]
    ] = []
    for rel in files_list:
        if rel in cached_set:
            merged.extend(cached_by_file.get(rel, []))
        else:
            merged.extend(stale_by_file.get(rel, []))
    return merged


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

def _raw_block_cache_row(
    stat: Statistic,
    meta: dict[str, str | int],
) -> dict[str, Any]:
    """Return the raw persisted row for a block statistic."""
    row = stat.as_dict()
    for key in list(row):
        if key in DERIVED_BLOCK_CACHE_KEYS or key.startswith("norm_"):
            del row[key]
    row.update(meta)
    return row


def statistic_from_raw_block_row(
    row: dict[str, Any],
    score_metrics: Iterable[str],
    *,
    smell_weight: float = 0.0,
    merged_config: dict[str, Any] | None = None,
    similarity_enabled: bool = True,
) -> Statistic:
    """Derive a scored ``Statistic`` from one raw cached block row."""
    path = str(row.get("path", ""))
    if path.startswith("__"):
        return Statistic(
            path=path,
            sloc=int(row.get("sloc", 0)),
            normalized_sloc=float(row.get("normalized_sloc", 0.0)),
            cyclomatic=int(row.get("cyclomatic", 0)),
            halstead=int(row.get("halstead", 0)),
            maintainability=int(row.get("maintainability", 0)),
            churn=int(row.get("churn", 0)),
            churn_per_sloc=float(row.get("churn_per_sloc", 0.0)),
            decayed_churn=float(row.get("decayed_churn", 0.0)),
            decayed_churn_per_sloc=float(row.get("decayed_churn_per_sloc", 0.0)),
            smell_count=int(row.get("smell_count", 0)),
            smell_severity=float(row.get("smell_severity", 0.0)),
            smell_burden=float(row.get("smell_burden", 0.0)),
            smells=dict(row.get("smells") or {}),
            similarity_score=float(row.get("similarity_score", 0.0)),
            similarity_band=str(row.get("similarity_band", "n/a")),
            match_count=int(row.get("match_count", 0)),
            score=float(row.get("score", 0.0)),
            score_band=str(row.get("score_band", "n/a")),
            score_subscores=dict(row.get("score_subscores") or {}),
            score_driver=str(row.get("score_driver", "")),
            score_explanation=_explain.sanitize_score_explanation_entries(
                row.get("score_explanation") or []
            ),
        )
    metrics = {
        "normalized_sloc": float(row.get("normalized_sloc", 0.0)),
        "cyclomatic": float(row.get("cyclomatic", 0.0)),
        "halstead": float(row.get("halstead", 0.0)),
        "maintainability": float(row.get("maintainability", 0.0)),
        "churn": float(row.get("churn", 0.0)),
        "churn_per_sloc": float(row.get("churn_per_sloc", 0.0)),
        "decayed_churn": float(row.get("decayed_churn", 0.0)),
        "decayed_churn_per_sloc": float(row.get("decayed_churn_per_sloc", 0.0)),
        "smell_count": float(row.get("smell_count", 0.0)),
        "smell_severity": float(row.get("smell_severity", 0.0)),
        "smell_burden": float(row.get("smell_burden", 0.0)),
        "similarity_score": float(row.get("similarity_score", 0.0)),
    }
    stat = Statistic(
        path=path,
        sloc=int(row.get("sloc", 0)),
        normalized_sloc=metrics["normalized_sloc"],
        cyclomatic=int(metrics["cyclomatic"]),
        halstead=int(metrics["halstead"]),
        maintainability=int(metrics["maintainability"]),
        churn=int(metrics["churn"]),
        churn_per_sloc=metrics["churn_per_sloc"],
        decayed_churn=metrics["decayed_churn"],
        decayed_churn_per_sloc=metrics["decayed_churn_per_sloc"],
        smell_count=int(metrics["smell_count"]),
        smell_severity=metrics["smell_severity"],
        smell_burden=metrics["smell_burden"],
        smells=dict(row.get("smells") or {}),
        similarity_score=metrics["similarity_score"],
        similarity_band=str(row.get("similarity_band", "n/a")),
        match_count=int(row.get("match_count", 0)),
        score=_score(metrics, score_metrics, smell_weight=smell_weight),
        score_driver="",
        score_explanation=[],
    )
    cfg = merged_config if merged_config is not None else {}
    scored = [stat]
    _apply_risk_scores(scored, cfg, similarity_enabled)
    return scored[0]


def statistic_from_complete_dict(row: dict[str, Any]) -> Statistic:
    """Rebuild a scored :class:`Statistic` from :meth:`Statistic.as_dict` output."""
    smells_raw = row.get("smells")
    smells: dict[str, Any] = dict(smells_raw) if isinstance(smells_raw, dict) else {}
    subs_raw = row.get("score_subscores")
    if isinstance(subs_raw, dict):
        subs = {str(k): float(v) for k, v in subs_raw.items()}
    else:
        subs = {}
    expl_raw = row.get("score_explanation")
    expl: list[dict[str, Any]] = (
        _explain.sanitize_score_explanation_entries(expl_raw)
        if isinstance(expl_raw, list)
        else []
    )
    sfw_raw = row.get("score_final_weights")
    sfw: dict[str, float] | None = None
    if isinstance(sfw_raw, dict) and sfw_raw:
        sfw = {str(k): float(v) for k, v in sfw_raw.items()}
    sni_raw = row.get("score_norm_inputs")
    sni: dict[str, dict[str, float]] | None = None
    if isinstance(sni_raw, dict) and sni_raw:
        sni = {}
        for bk, inner in sni_raw.items():
            if not isinstance(inner, dict):
                continue
            sni[str(bk)] = {str(k): float(v) for k, v in inner.items()}
    st = Statistic(
        path=str(row.get("path", "")),
        sloc=int(row.get("sloc", 0)),
        normalized_sloc=float(row.get("normalized_sloc", 0.0)),
        cyclomatic=int(row.get("cyclomatic", 0)),
        halstead=int(row.get("halstead", 0)),
        maintainability=int(row.get("maintainability", 0)),
        churn=int(row.get("churn", 0)),
        churn_per_sloc=float(row.get("churn_per_sloc", 0.0)),
        decayed_churn=float(row.get("decayed_churn", 0.0)),
        decayed_churn_per_sloc=float(row.get("decayed_churn_per_sloc", 0.0)),
        smell_count=int(row.get("smell_count", 0)),
        smell_severity=float(row.get("smell_severity", 0.0)),
        smell_burden=float(row.get("smell_burden", 0.0)),
        smells={str(k): int(v) for k, v in smells.items()},
        similarity_score=float(row.get("similarity_score", 0.0)),
        similarity_band=str(row.get("similarity_band", "n/a")),
        match_count=int(row.get("match_count", 0)),
        score=float(row.get("score", 0.0)),
        score_band=str(row.get("score_band", "n/a")),
        score_subscores=subs,
        score_driver=str(row.get("score_driver", "")),
        score_explanation=expl,
        score_final_weights=sfw,
        score_norm_inputs=sni,
    )
    if subs and not expl:
        st = replace(
            st,
            score_explanation=_explain.build_score_explanation(st, final_weights=sfw),
            score_driver=_explain.score_driver_from_subscores(subs, final_weights=sfw),
        )
    return st


def derive_block_statistics(
    rows: Iterable[dict[str, Any]],
    merged_config: dict[str, Any],
    *,
    score_metrics: Iterable[str] | None = None,
    smell_weight: float = 0.0,
    similarity_enabled: bool | None = None,
) -> list[Statistic]:
    """Derive scored block statistics from raw cached rows and active config."""
    cfg_score_metrics = (
        list(score_metrics)
        if score_metrics is not None
        else list(merged_config.get("score_metrics") or [])
    )
    sim_enabled = (
        bool(merged_config.get("similarity_enabled", True))
        if similarity_enabled is None
        else similarity_enabled
    )
    out: list[Statistic] = []
    for row in rows:
        if not isinstance(row, dict) or not str(row.get("path", "")).strip():
            continue
        out.append(
            statistic_from_raw_block_row(
                row,
                cfg_score_metrics,
                smell_weight=smell_weight,
                merged_config=merged_config,
                similarity_enabled=sim_enabled,
            )
        )
    return out


def derive_block_score_rows(
    rows: Iterable[dict[str, Any]],
    merged_config: dict[str, Any],
    *,
    score_metrics: Iterable[str] | None = None,
    smell_weight: float = 0.0,
    similarity_enabled: bool | None = None,
) -> list[dict[str, Any]]:
    """Return scored dict rows derived from raw cached rows."""
    return [
        stat.as_dict()
        for stat in derive_block_statistics(
            rows,
            merged_config,
            score_metrics=score_metrics,
            smell_weight=smell_weight,
            similarity_enabled=similarity_enabled,
        )
    ]


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
        cache_rows.append(_raw_block_cache_row(stat, meta))

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

