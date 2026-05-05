"""Block-level similarity using DeepCSIM (AST-based function comparison).

Pairwise composite similarity is computed between the outer ``def`` / ``async def``
in each block snippet (same boundaries as churn/radon). When the block count
exceeds ``similarity_max_pairwise_blocks``, we fall back to AST-hash clustering
only (exact structural clones), to keep runtime bounded.
"""
from __future__ import annotations

import ast
import warnings
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from hotspottriage import blocks as _blocks

_HAS_DEEPCSIM: bool
try:
    from deepcsim.core.analyzer import CodeAnalyzer
    from deepcsim.core.metrics import FunctionMetrics
    from deepcsim.core.similarity import SimilarityCalculator

    _HAS_DEEPCSIM = True
except ImportError:  # pragma: no cover
    _HAS_DEEPCSIM = False
    CodeAnalyzer = Any  # type: ignore[misc, assignment]
    FunctionMetrics = Any  # type: ignore[misc, assignment]
    SimilarityCalculator = Any  # type: ignore[misc, assignment]


@dataclass(frozen=True)
class BlockSimEntry:
    path: str  # "file.py::block.name"
    snippet: str


@dataclass(frozen=True)
class BlockSimMetrics:
    similarity_score: float
    similarity_band: str
    match_count: int


def metrics_for_block_snippet(snippet: str, logical_path: str) -> Any:
    """Extract DeepCSIM metrics for the first top-level function in a snippet."""
    if not _HAS_DEEPCSIM:
        return None
    try:
        tree = ast.parse(snippet, filename=logical_path)
    except SyntaxError:
        return None
    outer: ast.FunctionDef | ast.AsyncFunctionDef | None = None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            outer = node
            break
    if outer is None:
        return None
    try:
        ca = CodeAnalyzer(snippet, logical_path)
        ca.analyze()
    except (ValueError, SyntaxError):
        return None
    return ca.functions.get(outer.name)


def _band_for(
    best_score: float,
    match_count: int,
    *,
    high: float,
    medium: float,
    low: float,
) -> str:
    if best_score >= high or match_count >= 3:
        return "high"
    if best_score >= medium or match_count >= 1:
        return "medium"
    if best_score >= low:
        return "low"
    return "none"


def compute_pairwise_similarity(
    entries: list[BlockSimEntry],
    snippets: list[str],
    *,
    threshold: float,
    band_high: float,
    band_medium: float,
    band_low: float,
    max_pairwise_blocks: int,
) -> tuple[list[BlockSimMetrics], dict[str, Any]]:
    """Return per-entry metrics plus a small aggregate dict for a summary row."""
    n = len(entries)
    empty_agg: dict[str, Any] = {
        "blocks_total": n,
        "blocks_with_metrics": 0,
        "mean_similarity_score": 0.0,
        "total_match_usages": 0,
        "mode": "disabled",
    }
    if n == 0:
        return [], {}

    if not _HAS_DEEPCSIM:
        warnings.warn(
            "deepcsim is not installed; block similarity metrics will be zeros",
            stacklevel=2,
        )
        return (
            [BlockSimMetrics(0.0, "none", 0) for _ in range(n)],
            {**empty_agg, "mode": "missing_dependency"},
        )

    metrics: list[Any] = []
    for ent, snip in zip(entries, snippets):
        metrics.append(metrics_for_block_snippet(snip, ent.path))

    usable = sum(1 for m in metrics if m is not None)
    if usable == 0 and n > 0:
        warnings.warn(
            "DeepCSIM could not extract metrics from any block snippet "
            "(no parsable top-level def in snippet, syntax error, or analyzer failure); "
            "similarity_score stays 0 for every row.",
            stacklevel=2,
        )
    out: list[BlockSimMetrics] = []

    if n > max_pairwise_blocks:
        buckets: dict[str, list[int]] = defaultdict(list)
        for i, m in enumerate(metrics):
            if m is None:
                continue
            buckets[m.ast_hash].append(i)
        for i, m in enumerate(metrics):
            if m is None:
                out.append(BlockSimMetrics(0.0, "none", 0))
                continue
            peers = buckets[m.ast_hash]
            dupes = len(peers) - 1
            score = 100.0 if dupes > 0 else 0.0
            band = _band_for(score, dupes, high=band_high, medium=band_medium, low=band_low)
            out.append(BlockSimMetrics(score, band, dupes))
        mean_score = sum(b.similarity_score for b in out) / n if n else 0.0
        agg = {
            "blocks_total": n,
            "blocks_with_metrics": usable,
            "mean_similarity_score": round(mean_score, 4),
            "total_match_usages": sum(b.match_count for b in out) // 2,
            "mode": "hash_bucketing_only_over_cap",
            "max_pairwise_blocks": max_pairwise_blocks,
        }
        return out, agg

    for i, mi in enumerate(metrics):
        if mi is None:
            out.append(BlockSimMetrics(0.0, "none", 0))
            continue
        best = 0.0
        matches = 0
        for j, mj in enumerate(metrics):
            if i == j or mj is None:
                continue
            composite: float = SimilarityCalculator.calculate_all(mi, mj)["composite"]
            if composite > best:
                best = composite
            if composite >= threshold:
                matches += 1
        band = _band_for(best, matches, high=band_high, medium=band_medium, low=band_low)
        out.append(BlockSimMetrics(round(best, 4), band, matches))

    mean_score = sum(b.similarity_score for b in out) / n if n else 0.0
    agg = {
        "blocks_total": n,
        "blocks_with_metrics": usable,
        "mean_similarity_score": round(mean_score, 4),
        "total_match_usages": sum(b.match_count for b in out) // 2,
        "mode": "pairwise",
    }
    return out, agg


def attach_similarity_to_rows(
    rows_blocks: list[tuple[str, _blocks.Block, dict[str, float]]],
    file_sources: dict[str, str],
    *,
    similarity_enabled: bool,
    similarity_threshold: float,
    similarity_band_high: float,
    similarity_band_medium: float,
    similarity_band_low: float,
    similarity_max_pairwise_blocks: int,
) -> dict[str, Any] | None:
    """Mutate each metrics dict with similarity_* keys; return aggregate dict or None."""
    from hotspottriage import complexity as _complexity

    for _, _, m in rows_blocks:
        m.setdefault("similarity_score", 0.0)
        m.setdefault("similarity_band", "off")
        m.setdefault("match_count", 0.0)

    if not similarity_enabled or not rows_blocks:
        return None

    entries: list[BlockSimEntry] = []
    snippets: list[str] = []
    for rel, b, m in rows_blocks:
        src = file_sources[rel]
        snippet = _complexity.slice_block(src, b.start, b.end)
        entries.append(BlockSimEntry(path=f"{rel}::{b.name}", snippet=snippet))
        snippets.append(snippet)

    sims, agg = compute_pairwise_similarity(
        entries,
        snippets,
        threshold=similarity_threshold,
        band_high=similarity_band_high,
        band_medium=similarity_band_medium,
        band_low=similarity_band_low,
        max_pairwise_blocks=similarity_max_pairwise_blocks,
    )

    for (_, _, m), sim in zip(rows_blocks, sims):
        m["similarity_score"] = float(sim.similarity_score)
        m["similarity_band"] = sim.similarity_band
        m["match_count"] = float(sim.match_count)

    return agg

