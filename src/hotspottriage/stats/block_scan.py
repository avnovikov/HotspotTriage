"""Pass 1: scan tracked files, extract blocks, collect churn request tuples."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from hotspottriage import blocks as _blocks
from hotspottriage import complexity as _complexity

from hotspottriage.stats.block_context import BlockAnalysisContext


def scan_files_for_blocks(
    ctx: BlockAnalysisContext,
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
