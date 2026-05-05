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
from hotspottriage import cache as _cache
from hotspottriage import cache_generator as _cache_gen
from hotspottriage import config as _config
from hotspottriage import blocks as _blocks
from hotspottriage import discovery, filtering, output, stats

logger = logging.getLogger(__name__)
mcp = FastMCP("hotspottriage")


@mcp.tool()
def analyze_with_cache(
    target: str,
    filter: str | None = None,
    score_metrics: str | None = None,
    limit: int | None = None,
    since: str | None = None,
    until: str | None = None,
    respect_gitignore: bool = True,
    ignore_dir: str | None = None,
) -> str:
    """Analyze a repository with block-level caching.

    Generates and caches block-level metrics (functions/methods) for faster
    subsequent runs. The cache is stored in <repo>/.hotspottriage/cache/blocks.pkl.

    Args:
        target: Path to a local git repo
        filter: Comma-separated glob patterns
        score_metrics: Metrics to compute score from (default: churn_per_sloc,cyclomatic)
        limit: Maximum results to return
        since: Git --since date filter
        until: Git --until date filter
        respect_gitignore: Apply .gitignore rules (default: true)
        ignore_dir: Comma-separated directory prefixes to skip

    Returns:
        JSON list of block-level statistics with cache metadata
    """
    try:
        # Build config for block granularity analysis
        cfg = _build_analyze_config(
            filter=filter,
            score_metrics=score_metrics,
            granularity="block",
            limit=limit,
            directories=False,
            sort="score",
            since=since,
            until=until,
            respect_gitignore=respect_gitignore,
            ignore_dir=ignore_dir,
        )

        # Run block-level analysis (which generates and caches metrics)
        results = _analyze_repository(target, cfg)

        # Get cache info
        cache_info = _initialize_repository(target, cfg)

        # Format results with cache metadata
        results_list = [r.as_dict() for r in results]
        response = {
            "results": results_list,
            "cache": cache_info,
        }
        return json.dumps(response, indent=2)

    except Exception as e:
        logger.exception("Cache-backed analysis failed")
        return json.dumps({"error": str(e)})


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
def cache_status(target: str) -> str:
    """Check cache status and statistics for a repository.

    Args:
        target: Path to a local git repo

    Returns:
        JSON with cache statistics (size, entries, age)
    """
    try:
        repo_path = Path(target)
        cache_dir = _cache.cache_path_for(repo_path)

        if not cache_dir.exists():
            return json.dumps({
                "status": "empty",
                "message": "No cache directory found",
                "cache_dir": str(cache_dir),
                "entries": 0,
                "size_bytes": 0,
            })

        # Count cache entries and size
        cache_file = cache_dir / "blocks.pkl"
        entries = 0
        size_bytes = 0

        if cache_file.exists():
            size_bytes = cache_file.stat().st_size
            try:
                import pickle
                with open(cache_file, "rb") as f:
                    data = pickle.load(f)
                    entries = len(data) if isinstance(data, dict) else 0
            except Exception as e:
                return json.dumps({
                    "status": "error",
                    "message": f"Failed to read cache: {str(e)}",
                })

        return json.dumps({
            "status": "ok",
            "cache_dir": str(cache_dir),
            "entries": entries,
            "size_bytes": size_bytes,
            "cache_file": str(cache_file) if cache_file.exists() else None,
        })

    except Exception as e:
        logger.exception("Cache status check failed")
        return json.dumps({"status": "error", "message": str(e)})


@mcp.tool()
def clear_cache(target: str) -> str:
    """Clear the block-level cache for a repository.

    Args:
        target: Path to a local git repo

    Returns:
        Status message
    """
    try:
        repo_path = Path(target)
        cache_dir = _cache.cache_path_for(repo_path)

        if not cache_dir.exists():
            return json.dumps({
                "status": "success",
                "message": "No cache to clear",
            })

        # Remove cache files
        import shutil
        cache_file = cache_dir / "blocks.pkl"
        if cache_file.exists():
            cache_file.unlink()

        # Remove directory if empty
        try:
            cache_dir.rmdir()
        except OSError:
            pass  # Directory not empty, that's ok

        return json.dumps({
            "status": "success",
            "message": f"Cleared cache in {cache_dir}",
        })

    except Exception as e:
        logger.exception("Cache clear failed")
        return json.dumps({"status": "error", "message": str(e)})


@mcp.tool()
def analyze_classes(
    target: str,
    filter: str | None = None,
) -> str:
    """Analyze classes and their methods in Python files (file/class/method granularity).

    Args:
        target: Path to a local git repo
        filter: Comma-separated glob patterns to filter files

    Returns:
        JSON list with file, class, and method information including metrics
    """
    try:
        repo_path = Path(target)

        # Build filter config
        cfg = _config.DEFAULTS.copy()
        if filter:
            cfg["filter"] = [f.strip() for f in filter.split(",")]

        # Discover and filter files
        with discovery.resolve_target(target) as repo:
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

            # Extract class and method information
            results = []
            for file_path in files:
                full_path = repo / file_path
                try:
                    src = full_path.read_text(encoding="utf-8")
                    blocks = _blocks.extract_blocks(src)

                    for block in blocks:
                        # Parse block name to get class/method hierarchy
                        parts = block.name.split(".")
                        if len(parts) > 1:
                            # It's a method (or nested function)
                            class_name = parts[0] if len(parts) >= 1 else None
                            method_name = parts[-1]
                            parent = ".".join(parts[:-1])
                        else:
                            # Top-level function
                            class_name = None
                            method_name = parts[0]
                            parent = None

                        results.append({
                            "file": str(file_path),
                            "class": class_name,
                            "method": method_name,
                            "full_name": block.name,
                            "start_line": block.start,
                            "end_line": block.end,
                            "lines": block.end - block.start + 1,
                        })
                except Exception as e:
                    logger.warning(f"Failed to analyze {file_path}: {e}")

        return json.dumps(results, indent=2)

    except Exception as e:
        logger.exception("Class analysis failed")
        return json.dumps({"error": str(e)})


@mcp.tool()
def generate_cache(
    target: str,
    filter: str | None = None,
    score_metrics: str = "churn_per_sloc,cyclomatic",
) -> str:
    """Generate comprehensive codebase cache (blocks + classes/methods).

    Creates a complete snapshot including block-level metrics with churn data
    and class/method structure analysis. Results are cached in
    <repo>/.hotspottriage/cache/blocks.pkl.

    Args:
        target: Path to a local git repo
        filter: Comma-separated glob patterns
        score_metrics: Metrics to compute score from (default: churn_per_sloc,cyclomatic)

    Returns:
        JSON with complete cache including blocks, classes, and status
    """
    try:
        cache_data = _cache_gen.generate_full_cache(
            target=target,
            filter=filter,
            score_metrics=score_metrics,
            verbose=False,
        )
        return json.dumps(cache_data, indent=2)
    except Exception as e:
        logger.exception("Cache generation failed")
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
            # init_config currently returns a single Path for global scope.
            files = [str(written)] if isinstance(written, Path) else [str(f) for f in written]
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


def _initialize_repository(target: str, cfg: dict[str, Any]) -> dict[str, Any]:
    """Initialize repository cache with all metrics (blocks and churn).

    Caches block-level metrics for fast subsequent analysis. Returns cache
    statistics but not results.

    Returns: {"cache_file": str, "entries": int, "size_bytes": int}
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

        # Build block-level cache
        stats.build_block_stats(
            repo, files, score_metrics,
            since=cfg["since"], until=cfg["until"],
            workers=cfg.get("block_workers"),
            decay_half_life=cfg.get("decay_half_life"),
        )

        # Return cache info
        cache_dir = _cache.cache_path_for(repo)
        cache_file = cache_dir / "blocks.pkl"
        cache_size = cache_file.stat().st_size if cache_file.exists() else 0

        # Count entries
        entries = 0
        if cache_file.exists():
            try:
                import pickle
                with open(cache_file, "rb") as f:
                    data = pickle.load(f)
                    entries = len(data) if isinstance(data, dict) else 0
            except Exception:
                pass

        return {
            "cache_file": str(cache_file),
            "entries": entries,
            "size_bytes": cache_size,
        }


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
        decay_half_life = cfg.get("decay_half_life")
        if cfg["granularity"] == "block":
            results = stats.build_block_stats(
                repo, files, score_metrics,
                since=cfg["since"], until=cfg["until"],
                workers=cfg.get("block_workers"),
                decay_half_life=decay_half_life,
            )
        else:
            churn = _churn.compute_churn(
                repo, since=cfg["since"], until=cfg["until"]
            )
            results = stats.build_stats(
                repo, files, churn, score_metrics, decay_half_life=decay_half_life
            )
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
