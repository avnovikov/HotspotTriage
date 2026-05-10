"""High-level analyze paths: snapshot compare and live analysis with optional delta."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from hotspottriage import revision_cache as _rev_cache
from hotspottriage import cache as ht_cache
from hotspottriage import stats
from hotspottriage.mcp.analyze_args import AnalyzeInputs
from hotspottriage.mcp.analyze_pipeline import analyze_repository
from hotspottriage.mcp.block_delta_report import build_block_delta_report


def run_snapshot_compare(
    inputs: AnalyzeInputs,
) -> tuple[list[stats.Statistic], dict[str, Any], str]:
    """Compare two cached revision snapshots (both SHAs must exist).

    Returns ``(after_rows, deltas_dict, resolved_after_sha)``.
    """
    assert inputs.local_repo is not None, "snapshot compare requires a local repo"
    assert inputs.before_sha and inputs.after_sha

    mgr = _rev_cache.RevisionCacheManager(inputs.local_repo)
    try:
        after_rows = mgr.get_snapshot_statistics(inputs.after_sha)
        before_rows = mgr.get_snapshot_statistics(inputs.before_sha)
    except _rev_cache.SnapshotNotFoundError as e:
        raise ValueError(str(e)) from e

    deltas = build_block_delta_report(after_rows, before_rows)
    after_resolved = _rev_cache.resolve_commit_sha(
        inputs.local_repo, inputs.after_sha
    )
    return after_rows, deltas, after_resolved


def run_live_analysis(
    inputs: AnalyzeInputs,
    *,
    get_cache_manager: Callable[[Path], ht_cache.BlockCacheManager],
    progress_callback: Callable[[str, int, int], None] | None = None,
) -> tuple[list[stats.Statistic], str | None, dict[str, Any] | None]:
    """Run analysis at HEAD, record snapshot, optionally diff against *before_sha*.

    Returns ``(results_full, head_sha, deltas_or_none)``.
    """
    results_full = analyze_repository(
        inputs.analysis_root,
        inputs.cfg,
        get_cache_manager=get_cache_manager,
        apply_limit=False,
        progress_callback=progress_callback,
    )

    head_sha: str | None = None
    if inputs.local_repo is not None:
        head_sha = _rev_cache.RevisionCacheManager(
            inputs.local_repo
        ).record_snapshot(results_full)

    deltas: dict[str, Any] | None = None
    if inputs.before_sha:
        assert inputs.local_repo is not None
        mgr = _rev_cache.RevisionCacheManager(inputs.local_repo)
        try:
            before_rows = mgr.get_snapshot_statistics(inputs.before_sha)
        except _rev_cache.SnapshotNotFoundError as e:
            raise ValueError(str(e)) from e
        deltas = build_block_delta_report(results_full, before_rows)

    return results_full, head_sha, deltas
