"""FastMCP server for HotspotTriage.

Exposes analyze and init_config as MCP tools for Claude and other AI assistants.

Usage:
    hotspottriage-mcp  # Runs as an MCP server on stdio
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from hotspottriage import churn as _churn
from hotspottriage import config as _config
from hotspottriage import discovery, filtering, output, stats

logger = logging.getLogger(__name__)
mcp = FastMCP("hotspottriage")


@mcp.tool()
def analyze(
    target: str,
    filter: str | None = None,
    score_metrics: str | None = None,
    granularity: str = "file",
    limit: int | None = None,
    format: str = "json",
    directories: bool = False,
    sort: str = "score",
    since: str | None = None,
    until: str | None = None,
    respect_gitignore: bool = True,
    ignore_dir: str | None = None,
) -> str:
    """Analyze a git repository for code complexity and churn hotspots.

    Args:
        target: Path to a local git repo or remote git URL
        filter: Comma-separated glob patterns (AND semantics, '!' negates)
        score_metrics: Comma-separated metrics to compute score from
                      (default: churn_per_sloc,cyclomatic)
                      Available: sloc, cyclomatic, halstead, maintainability, churn, churn_per_sloc
        granularity: 'file' (default) or 'block' (per-function analysis)
        limit: Maximum number of results to return
        format: 'json' (default) or 'table'
        directories: Aggregate by directory instead of file
        sort: 'score' (default) or 'file'
        since: Git --since date filter
        until: Git --until date filter
        respect_gitignore: Apply .gitignore rules (default: true)
        ignore_dir: Comma-separated directory prefixes to skip

    Returns:
        JSON-formatted analysis results
    """
    try:
        # Parse arguments into config
        cfg = _build_analyze_config(
            filter=filter,
            score_metrics=score_metrics,
            granularity=granularity,
            limit=limit,
            directories=directories,
            sort=sort,
            since=since,
            until=until,
            respect_gitignore=respect_gitignore,
            ignore_dir=ignore_dir,
        )

        # Run analysis
        results = _analyze_repository(target, cfg)

        # Format results
        results_list = [r.as_dict() for r in results]
        return json.dumps(results_list, indent=2)

    except Exception as e:
        logger.exception("Analysis failed")
        return json.dumps({"error": str(e)})


@mcp.tool()
def init_config(target: str = "", is_global: bool = False) -> str:
    """Initialize HotspotTriage configuration files.

    Args:
        target: Path to git repository (empty/unused if is_global=True)
        is_global: Initialize global config (~/.hotspottriage/) instead of project config

    Returns:
        Status message with list of files created
    """
    try:
        if is_global:
            written = _config.init_config(scope="global")
            # Global scope returns a list
            files = [str(f) for f in written]
            return json.dumps({
                "status": "success",
                "message": f"Initialized global config",
                "files": files,
            })
        else:
            target = target or "."
            repo_path = Path(target)
            written = _config.init_config(scope="project", target=repo_path)
            # Project scope returns a single Path, convert to list
            files = [str(written)] if isinstance(written, Path) else [str(f) for f in written]
            return json.dumps({
                "status": "success",
                "message": f"Initialized project config in {repo_path / _config.PROJECT_CONFIG_DIRNAME}",
                "files": files,
            })

    except Exception as e:
        logger.exception("Config init failed")
        return json.dumps({"status": "error", "message": str(e)})


def _build_analyze_config(
    filter: str | None = None,
    score_metrics: str | None = None,
    granularity: str = "file",
    limit: int | None = None,
    directories: bool = False,
    sort: str = "score",
    since: str | None = None,
    until: str | None = None,
    respect_gitignore: bool = True,
    ignore_dir: str | None = None,
) -> dict[str, Any]:
    """Build analysis config from MCP tool arguments."""
    cfg = _config.DEFAULTS.copy()

    if filter:
        cfg["filter"] = [f.strip() for f in filter.split(",")]

    if score_metrics:
        cfg["score_metrics"] = [m.strip() for m in score_metrics.split(",")]

    cfg["granularity"] = granularity
    cfg["directories"] = directories
    cfg["sort"] = sort

    if limit is not None:
        cfg["limit"] = limit

    if since:
        cfg["since"] = since

    if until:
        cfg["until"] = until

    cfg["respect_gitignore"] = respect_gitignore

    if ignore_dir:
        cfg["ignore_directories"] = [d.strip() for d in ignore_dir.split(",")]

    return cfg


def _analyze_repository(target: str, cfg: dict[str, Any]) -> list[stats.Statistic]:
    """Run the full analysis pipeline.

    Mirrors the CLI flow from cli.py, using the same filtering and metrics computation.
    """
    with discovery.resolve_target(target) as repo:
        # Build filter predicates
        patterns = list(cfg["filter"])
        if not cfg["no_default_filter"]:
            patterns.append(cfg["default_filter"])

        glob_keep = filtering.make_filter(patterns)
        keep = filtering.make_tracked_path_predicate(
            repo,
            glob_keep=glob_keep,
            ignore_directories=cfg["ignore_directories"],
            respect_gitignore=cfg["respect_gitignore"],
        )
        files = [f for f in discovery.list_tracked_files(repo) if keep(f)]
        score_metrics = list(cfg["score_metrics"])

        # Compute metrics
        if cfg["granularity"] == "block":
            results = stats.build_block_stats(
                repo, files, score_metrics,
                since=cfg["since"], until=cfg["until"],
                workers=cfg.get("block_workers"),
            )
        else:
            churn = _churn.compute_churn(
                repo, since=cfg["since"], until=cfg["until"]
            )
            results = stats.build_stats(repo, files, churn, score_metrics)
            if cfg["directories"]:
                results = stats.aggregate_by_directory(results, score_metrics)

        # Sort and limit
        results = stats.sort_and_limit(
            results, by=cfg["sort"], limit=cfg["limit"]
        )

        return results


def main() -> None:
    """Entry point for the FastMCP server."""
    logging.basicConfig(level=logging.INFO)
    mcp.run()


if __name__ == "__main__":
    main()
