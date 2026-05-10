"""Publish block metrics to the optional MCP dashboard (DI, no FastMCP coupling)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from hotspottriage import discovery, stats
from hotspottriage.mcp.block_row_utils import block_metric_row_repo_file

logger = logging.getLogger(__name__)


def publish_block_metrics_to_dashboard(
    target: str,
    rows: list[stats.Statistic],
    cfg: dict[str, Any],
    *,
    get_dashboard_instance: Callable[[], Any | None],
) -> None:
    """Push raw block rows to the dashboard for heatmap/histogram endpoints."""
    if cfg.get("granularity") != "block":
        return
    dash = get_dashboard_instance()
    if dash is None:
        return
    analysis_repo: Path | None = None
    if not discovery.is_git_url(target):
        p = Path(target).expanduser().resolve()
        if p.is_dir():
            analysis_repo = p
    dash.publish_latest_block_metrics(
        [r.as_dict() for r in rows],
        analysis_repo=analysis_repo,
    )


def publish_manager_rows_to_dashboard(
    target: str,
    cfg: dict[str, Any],
    *,
    get_dashboard_instance: Callable[[], Any | None],
    get_cache_manager: Callable[[Path], Any],
    build_keep_predicate: Callable[[Path, dict[str, Any]], Callable[[str], bool]],
    synthetic_block_rows: list[dict[str, Any]] | None = None,
) -> None:
    """Push cache-manager rows to the dashboard, scoped to *cfg* filters."""
    dash = get_dashboard_instance()
    if dash is None:
        return
    try:
        with discovery.resolve_target(target) as repo:
            mgr = get_cache_manager(repo)
            rows = mgr.get_all_rows()
            keep = build_keep_predicate(repo, cfg)
            merged: dict[str, dict[str, Any]] = {}
            for r in rows:
                if not isinstance(r, dict):
                    continue
                p = r.get("path")
                if not isinstance(p, str):
                    continue
                fk = block_metric_row_repo_file(p)
                if keep(fk):
                    merged[p] = r
            if synthetic_block_rows:
                for row in synthetic_block_rows:
                    if isinstance(row, dict) and isinstance(row.get("path"), str):
                        merged[str(row["path"])] = row
            out = list(merged.values())
            if out:
                dash.publish_latest_block_metrics(out, analysis_repo=repo)
    except Exception:
        logger.debug("Publishing block metrics to dashboard skipped", exc_info=True)
