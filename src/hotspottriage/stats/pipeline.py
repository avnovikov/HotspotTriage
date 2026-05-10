"""Block-level scan, churn, assemble, and risk-score application."""
from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hotspottriage import block_churn as _block_churn
from hotspottriage import blocks as _blocks
from hotspottriage import complexity as _complexity
from hotspottriage.config import DEFAULTS as _DEFAULTS
from hotspottriage.stats import core as _core

logger = logging.getLogger(__name__)


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


def _process_single_file(
    repo: Path,
    rel: str,
    blob_sha: str,
    merged_config: dict[str, Any],
) -> tuple[
    str,
    str,
    dict[str, int],
    list[_blocks.Block],
    list[dict[str, Any]],
    list[tuple[str, str, int, int]],
] | None:
    """Process one file: read source, compute metrics/smells/blocks. Returns None on error."""
    from hotspottriage import smell as _smell

    try:
        src = (repo / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        logger.debug("Skipping unreadable file: %s", rel)
        return None
    metrics = _complexity.compute_all(repo / rel)
    smells = _smell.compute_smells(repo / rel, merged_config)
    blocks = _blocks.extract_blocks(src)
    reqs = [(rel, blob_sha, b.start, b.end) for b in blocks]
    return rel, src, metrics, blocks, smells, reqs


def _scan_files_for_blocks(
    ctx: _BlockAnalysisContext,
    progress_callback: Callable[[str, int, int], None] | None,
    workers: int | None = None,
) -> tuple[
    dict[str, dict[str, int]],
    dict[str, list[_blocks.Block]],
    dict[str, str],
    dict[str, list[dict[str, Any]]],
    list[tuple[str, str, int, int]],
]:
    """Pass 1: extract blocks + compute file/snippet metrics (parallel)."""
    file_metrics: dict[str, dict[str, int]] = {}
    file_blocks: dict[str, list[_blocks.Block]] = {}
    file_sources: dict[str, str] = {}
    file_smells: dict[str, list[dict[str, Any]]] = {}
    requests: list[tuple[str, str, int, int]] = []

    eligible = [(rel, ctx.blob_shas[rel]) for rel in ctx.files if rel in ctx.blob_shas]
    scan_total = len(eligible)
    if not scan_total:
        return file_metrics, file_blocks, file_sources, file_smells, requests

    effective_workers = workers or min(32, (os.cpu_count() or 4) * 2)
    progress_lock = threading.Lock()
    scan_done = 0

    if progress_callback:
        progress_callback("Scanning files", 0, scan_total)

    with ThreadPoolExecutor(max_workers=effective_workers) as executor:
        futures = {
            executor.submit(
                _process_single_file, ctx.repo, rel, blob_sha, ctx.merged_config
            ): rel
            for rel, blob_sha in eligible
        }
        for future in as_completed(futures):
            result = future.result()
            if result is None:
                with progress_lock:
                    scan_done += 1
                    if progress_callback:
                        progress_callback(f"Scanning (skipped)", scan_done, scan_total)
                continue
            rel, src, metrics, blocks, smells, reqs = result
            file_sources[rel] = src
            file_metrics[rel] = metrics
            file_smells[rel] = smells
            file_blocks[rel] = blocks
            requests.extend(reqs)
            with progress_lock:
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
        min_sloc = int(
            (ctx.merged_config or {}).get(
                "min_sloc_for_ratio", _DEFAULTS["min_sloc_for_ratio"]
            )
        )
        func_by_name = _smell.function_defs_by_qualname(src)
        smell_res_cfg = _smell.smell_resolution_cfg(ctx.merged_config)

        for b in file_blocks[rel]:
            snippet = _complexity.slice_block(src, b.start, b.end)
            m: dict[str, Any] = dict(_complexity.compute_for_source(snippet))
            m["maintainability"] = file_mi
            m["churn"] = churns.get((rel, b.start, b.end), 0)
            m["churn_per_sloc"] = _core._ratio(
                int(m["churn"]), int(m["sloc"]), min_sloc_for_ratio=min_sloc
            )
            m["decayed_churn"] = (
                _core._decayed_value(m["churn"], age_seconds, decay_half_life)
                if decay_half_life
                else m["churn"]
            )
            m["decayed_churn_per_sloc"] = _core._ratio(
                m["decayed_churn"], int(m["sloc"]), min_sloc_for_ratio=min_sloc
            )

            block_raw = [
                s for s in file_smells.get(rel, []) if _smell.finding_applies_to_block(s, b)
            ]
            merged_for_smell = ctx.merged_config if ctx.merged_config else _DEFAULTS
            tw = _smell.maybe_trivial_wrapper_block_finding(
                file_path=str(ctx.repo / rel),
                block=b,
                metrics=m,
                pylint_block_findings=block_raw,
                merged_config=merged_for_smell,
                func_node=func_by_name.get(b.name),
            )
            if tw is not None:
                tw["severity"] = _smell.resolve_smell_severity(tw, smell_res_cfg)
                block_raw.append(tw)
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


def _run_stale_pipeline(
    ctx: _BlockAnalysisContext,
    file_sources: dict[str, str],
    *,
    since: str | None,
    until: str | None,
    workers: int | None,
    decay_half_life: int | None,
    cached_scan_count: int,
    outer_scan_total: int,
    progress_callback: Callable[[str, int, int], None] | None,
) -> tuple[
    list[tuple[str, _blocks.Block, dict[str, Any]]],
    list[dict[str, str | int]],
]:
    """Run scan → churn → assemble for stale (changed) files only."""

    def _wrap_scan_progress(label: str, done: int, _inner_total: int) -> None:
        if progress_callback:
            progress_callback(label, cached_scan_count + done, outer_scan_total)

    scan_progress = _wrap_scan_progress if progress_callback else None

    file_metrics, file_blocks, file_sources_stale, file_smells, requests = (
        _scan_files_for_blocks(ctx, scan_progress, workers=workers)
    )
    file_sources.update(file_sources_stale)

    churns = _compute_block_churns(ctx, requests, since, until, workers, progress_callback)
    return _assemble_block_metrics(
        ctx, file_metrics, file_blocks, file_sources, file_smells, churns, decay_half_life
    )

