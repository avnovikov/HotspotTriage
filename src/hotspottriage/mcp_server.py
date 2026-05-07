"""FastMCP server for HotspotTriage.

Exposes analyze and init_config as MCP tools for Claude and other AI assistants.

Usage (stdio MCP server):
    hotspottriage start-mcp-server   # same layout as ``serena start-mcp-server``
    hotspottriage-mcp                # legacy console_scripts alias
"""
from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
from copy import deepcopy
import json
import logging
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from hotspottriage import churn as _churn
from hotspottriage import cache as _cache
from hotspottriage import cache_generator as _cache_gen
from hotspottriage import config as _config
from hotspottriage.dashboard.log_handler import MemoryLogHandler
from hotspottriage.dashboard.server import DashboardServer
from hotspottriage.dashboard.stats import StatsCollector
from hotspottriage import discovery, filtering, output as _output, stats

logger = logging.getLogger(__name__)

# Populated in :func:`main` before ``mcp.run()`` (used by dashboard lifespan).
_mcp_dashboard_cli: argparse.Namespace | None = None
_dashboard_stats = StatsCollector()
# Live dashboard instance when MCP enables the FastAPI server (block metrics publishing).
_dashboard_server_instance: DashboardServer | None = None
# Per-repo BlockCacheManagers, keyed by resolved repo path string.
_cache_managers: dict[str, _cache.BlockCacheManager] = {}
_cache_managers_lock = threading.Lock()
_dashboard_log_handler = MemoryLogHandler(
    max_records=int(_config.DEFAULTS["dashboard"]["max_log_records"])
)
_dashboard_log_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
)
if _dashboard_log_handler not in logging.getLogger().handlers:
    logging.getLogger().addHandler(_dashboard_log_handler)


def _get_cache_manager(repo: Path) -> _cache.BlockCacheManager:
    """Return (or create) the BlockCacheManager for *repo* (thread-safe)."""
    key = str(repo.resolve())
    with _cache_managers_lock:
        mgr = _cache_managers.get(key)
        if mgr is None:
            mgr = _cache.BlockCacheManager(repo, flush_interval_s=15.0)
            mgr.start_periodic_flush()
            _cache_managers[key] = mgr
        return mgr


def _shutdown_all_cache_managers() -> None:
    """Stop periodic flush on all managers (called at MCP shutdown)."""
    with _cache_managers_lock:
        for mgr in _cache_managers.values():
            mgr.stop()
        _cache_managers.clear()


def _ensure_root_logging_configured() -> None:
    """Keep dashboard logs visible even when root already has a handler.

    ``logging.basicConfig`` is a no-op when handlers already exist on the root
    logger. Because the dashboard handler is attached at import time, we must
    explicitly raise the root logger threshold from WARNING to INFO so routine
    tool-call logs appear in the dashboard.
    """
    root = logging.getLogger()
    if root.level > logging.INFO:
        root.setLevel(logging.INFO)
    logging.basicConfig(level=logging.INFO)


def get_mcp_dashboard_cli_args() -> argparse.Namespace | None:
    """Return parsed MCP dashboard flags (``start-mcp-server`` / ``hotspottriage-mcp``), or ``None`` before :func:`main`."""
    return _mcp_dashboard_cli


def _effective_dashboard_config() -> dict[str, Any]:
    cfg = dict(_config.DEFAULTS)
    cli = get_mcp_dashboard_cli_args()
    if cli is None:
        return cfg
    cfg = _config.apply_mcp_dashboard_cli_overrides(
        cfg,
        no_dashboard=bool(cli.no_dashboard),
        dashboard_port=cli.dashboard_port,
        dashboard_host=cli.dashboard_host,
        open_browser=bool(cli.open_browser),
    )
    return cfg


@asynccontextmanager
async def _mcp_lifespan(_: Any):
    global _dashboard_server_instance
    dashboard: DashboardServer | None = None
    cfg = _effective_dashboard_config()
    dash_cfg = dict(cfg.get("dashboard") or {})
    if bool(dash_cfg.get("enabled", True)):
        try:
            dashboard = DashboardServer(
                config=_config.to_dashboard_snapshot(cfg),
                stats=_dashboard_stats,
                log_handler=_dashboard_log_handler,
                host=str(dash_cfg.get("host", "127.0.0.1")),
                base_port=int(dash_cfg.get("base_port", 9123)),
                open_on_start=bool(dash_cfg.get("open_on_start", False)),
            )
            _dashboard_server_instance = dashboard
            dashboard.start()
            logger.info("HotspotTriage dashboard: %s/dashboard/", dashboard.base_url)
        except Exception as e:  # pragma: no cover - defensive path
            logger.warning("Dashboard startup failed: %s", e)
    yield
    _dashboard_server_instance = None
    _shutdown_all_cache_managers()


mcp = FastMCP("hotspottriage", lifespan=_mcp_lifespan)


def _parse_mcp_dashboard_argv() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="hotspottriage start-mcp-server",
        add_help=False,
        description="HotspotTriage MCP server (stdio). Dashboard flags are listed below; "
        "other arguments are forwarded to the MCP runtime. Same flags as `hotspottriage-mcp`.",
    )
    parser.add_argument(
        "--no-dashboard",
        action="store_true",
        help="Disable the local web dashboard for this process.",
    )
    parser.add_argument(
        "--dashboard-port",
        type=int,
        default=None,
        metavar="PORT",
        help="First TCP port to try for the dashboard (default from config).",
    )
    parser.add_argument(
        "--dashboard-host",
        type=str,
        default=None,
        metavar="HOST",
        help="Dashboard bind address (default from config).",
    )
    parser.add_argument(
        "--open-browser",
        action="store_true",
        help="Open the dashboard in a browser when the server starts.",
    )
    args, rest = parser.parse_known_args()
    sys.argv = [sys.argv[0], *rest]
    return args


def run_cached_block_analysis_dict(
    target: str,
    *,
    filter: str | None = None,
    score_metrics: str | None = None,
    limit: int | None = None,
    since: str | None = None,
    until: str | None = None,
    respect_gitignore: bool = True,
    ignore_dir: str | None = None,
    similarity: bool = True,
    compact: bool = True,
    sort: str = "score",
    progress_callback: Callable[[str, int, int], None] | None = None,
    config_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Block-level analysis + cache warm-up; returns ``results`` / ``cache`` dict (not JSON).

    Optional ``progress_callback(label, done, total)`` mirrors
    :func:`hotspottriage.stats.build_block_stats` progress events.
    """
    cfg = _build_analyze_config(
        target,
        filter=filter,
        score_metrics=score_metrics,
        granularity="block",
        limit=limit,
        directories=False,
        sort=sort,
        since=since,
        until=until,
        respect_gitignore=respect_gitignore,
        ignore_dir=ignore_dir,
        config_overrides=config_overrides,
    )
    cfg["similarity_enabled"] = similarity

    results_full = _analyze_repository(
        target, cfg, apply_limit=False, progress_callback=progress_callback
    )
    _publish_block_metrics_to_dashboard(results_full, cfg)
    results = stats.sort_and_limit(
        results_full, by=cfg["sort"], limit=cfg["limit"]
    )

    cache_info = _initialize_repository(
        target, cfg, progress_callback=progress_callback
    )
    # Publish live manager rows to dashboard after cache warm-up.
    _publish_manager_rows_to_dashboard(target)

    if compact:
        results_list = _mcp_compact_score_rows(
            results, granularity="block", merged_config=cfg
        )
    else:
        results_list = []
        for row in results:
            output_row = _output.statistic_to_output_dict(row, cfg)
            output_row["proposed_model"] = _proposed_model_for_band(
                str(row.score_band), cfg
            )
            results_list.append(output_row)
    return {
        "results": results_list,
        "cache": cache_info,
    }


def _run_analyze_cached(
    target: str,
    *,
    filter: str | None = None,
    score_metrics: str | None = None,
    limit: int | None = None,
    since: str | None = None,
    until: str | None = None,
    respect_gitignore: bool = True,
    ignore_dir: str | None = None,
    similarity: bool = True,
    compact: bool = True,
    sort: str = "score",
) -> str:
    """Block-level analysis with disk cache warm-up; returns JSON ``{results, cache}``."""
    try:
        response = run_cached_block_analysis_dict(
            target,
            filter=filter,
            score_metrics=score_metrics,
            limit=limit,
            since=since,
            until=until,
            respect_gitignore=respect_gitignore,
            ignore_dir=ignore_dir,
            similarity=similarity,
            compact=compact,
            sort=sort,
        )
        return json.dumps(response, indent=2)

    except Exception as e:
        logger.exception("Cache-backed analysis failed")
        return json.dumps({"error": str(e)})


@mcp.tool()
def analyze(
    target: str,
    filter: str | None = None,
    score_metrics: str | None = None,
    limit: int | None = None,
    sort: str = "score",
    since: str | None = None,
    until: str | None = None,
    respect_gitignore: bool = True,
    ignore_dir: str | None = None,
    similarity: bool = True,
    compact: bool = True,
) -> str:
    """Analyze a repository: block-level metrics, disk cache, and dashboard publish.

    Always runs the cache-backed block pipeline. Returns JSON
    ``{"results": [...], "cache": {...}}``.
    By default each result row is only ``function``, ``score``, and ``risk_band``.
    Leaving ``compact`` unset keeps this default compact output; set
    ``compact`` to false for full metric dicts.

    Args:
        target: Path to a local git repo or remote git URL
        filter: Comma-separated filters, matched against repo-relative POSIX paths.
            Globs use AND semantics ('!' negates). Example: ``*dashboard/*.py``
            only matches root-level ``<name>dashboard/<file>.py`` paths, while
            ``**/dashboard/*.py`` matches dashboard directories at any depth.
            Multiple literal file paths are treated as an include list.
        score_metrics: Comma-separated metrics for scoring (default: churn_per_sloc,cyclomatic)
        limit: Maximum number of block rows returned
        sort: 'score' (default) or 'file'
        since: Git --since date filter
        until: Git --until date filter
        respect_gitignore: Apply .gitignore rules (default: true)
        ignore_dir: Comma-separated directory prefixes to skip
        similarity: DeepCSIM similarity per block (default: true)
        compact: When true (default), each row is only ``function``, ``score``, ``risk_band``

    Returns:
        JSON object with ``results`` and ``cache`` keys, or ``{"error": ...}``
    """
    return _run_analyze_cached(
        target,
        filter=filter,
        score_metrics=score_metrics,
        limit=limit,
        since=since,
        until=until,
        respect_gitignore=respect_gitignore,
        ignore_dir=ignore_dir,
        similarity=similarity,
        compact=compact,
        sort=sort,
    )


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

        cache_file = cache_dir / _cache._CACHE_FILE
        entries = 0
        size_bytes = 0

        if cache_file.exists():
            size_bytes = cache_file.stat().st_size
            rows = _cache.load_block_results(repo_path)
            entries = len(rows) if rows else 0

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

        cache_file = cache_dir / _cache._CACHE_FILE
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
    target: str,
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
    config_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build analysis config from MCP tool arguments."""
    cfg = deepcopy(_config.DEFAULTS)
    local_target = Path(target).expanduser()
    if local_target.is_dir():
        cfg = _config.load_config(
            local_target.resolve(),
            use_global=False,
            use_project=True,
        )
        dashboard_patch = local_target.resolve() / ".hotspottriage" / "dashboard_config_patch.yml"
        if dashboard_patch.is_file():
            patch_data = _config._read_yaml(dashboard_patch)
            if patch_data:
                cfg = _config._deep_merge(cfg, patch_data)

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

    if config_overrides:
        cfg = _config._deep_merge(cfg, config_overrides)
        if filter:
            cfg["filter"] = [f.strip() for f in filter.split(",")]
        if score_metrics:
            cfg["score_metrics"] = [m.strip() for m in score_metrics.split(",")]

    return cfg


def _is_literal_filter_path(pattern: str) -> bool:
    """Return True when *pattern* looks like a concrete path, not a glob."""
    token = pattern.strip()
    if not token or token.startswith("!"):
        return False
    return not any(ch in token for ch in "*?[]{}")


def _normalize_filter_path(path: str) -> str:
    """Normalize a filter path to POSIX relative form for exact matching."""
    normalized = path.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _build_repo_keep_predicate(
    repo: Path,
    cfg: dict[str, Any],
) -> Callable[[str], bool]:
    """Build tracked-path predicate with MCP-friendly multi-file filter handling."""
    raw_patterns = [p.strip() for p in cfg["filter"] if p and p.strip()]
    use_literal_list = len(raw_patterns) > 1 and all(
        _is_literal_filter_path(p) for p in raw_patterns
    )

    if use_literal_list:
        allowed_paths = {_normalize_filter_path(p) for p in raw_patterns}

        def glob_keep(rel_posix: str) -> bool:
            return _normalize_filter_path(rel_posix) in allowed_paths

    else:
        patterns = list(cfg["filter"])
        if not cfg["no_default_filter"]:
            patterns.append(cfg["default_filter"])
        glob_keep = filtering.make_filter(patterns)

    return filtering.make_tracked_path_predicate(
        repo,
        glob_keep=glob_keep,
        ignore_directories=cfg["ignore_directories"],
        respect_gitignore=cfg["respect_gitignore"],
    )


def _initialize_repository(
    target: str,
    cfg: dict[str, Any],
    progress_callback: Callable[[str, int, int], None] | None = None,
) -> dict[str, Any]:
    """Initialize repository cache with all metrics (blocks and churn).

    Caches block-level metrics for fast subsequent analysis. Returns cache
    statistics but not results.

    Returns: {"cache_file": str, "entries": int, "size_bytes": int}
    """
    _config.validate(cfg)
    with discovery.resolve_target(target) as repo:
        keep = _build_repo_keep_predicate(repo, cfg)
        files = [f for f in discovery.list_tracked_files(repo) if keep(f)]
        score_metrics = list(cfg["score_metrics"])

        # Build block-level cache
        mgr = _get_cache_manager(repo)
        stats.build_block_stats(
            repo, files, score_metrics,
            since=cfg["since"], until=cfg["until"],
            workers=cfg.get("block_workers"),
            decay_half_life=cfg.get("decay_half_life"),
            smell_weight=float(cfg.get("smell_weight", 0.0)),
            progress_callback=progress_callback,
            merged_config=cfg,
            cache_manager=mgr,
            **stats.block_similarity_kwargs_from_config(cfg),
        )
        mgr.flush()

        # Return cache info from manager (live, not stale disk)
        cache_dir = _cache.cache_path_for(repo)
        cache_file = cache_dir / _cache._CACHE_FILE
        cache_size = cache_file.stat().st_size if cache_file.exists() else 0
        entries = mgr.entry_count

        return {
            "cache_file": str(cache_file),
            "entries": entries,
            "size_bytes": cache_size,
        }


def _mcp_compact_score_rows(
    rows: list[stats.Statistic], *, granularity: str, merged_config: dict[str, Any]
) -> list[dict[str, Any]]:
    """One dict per row: function symbol, score, risk band, proposed model."""
    out: list[dict[str, Any]] = []
    for r in rows:
        p = r.path
        if granularity == "block" and "::" in p:
            fn = p.split("::", 1)[1]
        else:
            fn = p
        score_band = str(r.score_band)
        out.append(
            {
                "function": fn,
                "score": float(r.score),
                "risk_band": score_band,
                "proposed_model": _proposed_model_for_band(score_band, merged_config),
            }
        )
    return out


def _proposed_model_for_band(score_band: str, merged_config: dict[str, Any]) -> str:
    proposed = merged_config.get("proposed_models")
    if not isinstance(proposed, dict):
        return ""
    model = proposed.get(score_band)
    return model if isinstance(model, str) else ""


def _publish_block_metrics_to_dashboard(
    rows: list[stats.Statistic],
    cfg: dict[str, Any],
) -> None:
    """Push raw block rows to the dashboard for heatmap/histogram endpoints."""
    if cfg.get("granularity") != "block":
        return
    dash = _dashboard_server_instance
    if dash is None:
        return
    dash.publish_latest_block_metrics([r.as_dict() for r in rows])


def _publish_manager_rows_to_dashboard(target: str) -> None:
    """Push the live cache-manager rows to the dashboard."""
    dash = _dashboard_server_instance
    if dash is None:
        return
    try:
        repo = Path(target).resolve()
        mgr = _get_cache_manager(repo)
        rows = mgr.get_all_rows()
        if rows:
            dash.publish_latest_block_metrics(rows)
    except Exception:
        pass


def _analyze_repository(
    target: str,
    cfg: dict[str, Any],
    *,
    apply_limit: bool = True,
    progress_callback: Callable[[str, int, int], None] | None = None,
) -> list[stats.Statistic]:
    """Run the full analysis pipeline.

    Mirrors the CLI flow from cli.py, using the same filtering and metrics computation.
    """
    _config.validate(cfg)
    with discovery.resolve_target(target) as repo:
        keep = _build_repo_keep_predicate(repo, cfg)
        files = [f for f in discovery.list_tracked_files(repo) if keep(f)]
        score_metrics = list(cfg["score_metrics"])

        # Compute metrics
        decay_half_life = cfg.get("decay_half_life")
        smell_weight = float(cfg.get("smell_weight", 0.0))
        mgr = _get_cache_manager(repo)
        if cfg["granularity"] == "block":
            results = stats.build_block_stats(
                repo, files, score_metrics,
                since=cfg["since"], until=cfg["until"],
                workers=cfg.get("block_workers"),
                decay_half_life=decay_half_life,
                smell_weight=smell_weight,
                progress_callback=progress_callback,
                merged_config=cfg,
                cache_manager=mgr,
                **stats.block_similarity_kwargs_from_config(cfg),
            )
        else:
            churn = _churn.compute_churn(
                repo, since=cfg["since"], until=cfg["until"]
            )
            results = stats.build_stats(
                repo,
                files,
                churn,
                score_metrics,
                decay_half_life=decay_half_life,
                smell_weight=smell_weight,
                merged_config=cfg,
            )
            if cfg["directories"]:
                results = stats.aggregate_by_directory(
                    results, score_metrics, smell_weight=smell_weight
                )

        lim = cfg["limit"] if apply_limit else None
        return stats.sort_and_limit(results, by=cfg["sort"], limit=lim)


def main() -> None:
    """Entry point for the FastMCP server."""
    global _mcp_dashboard_cli
    _mcp_dashboard_cli = _parse_mcp_dashboard_argv()
    _ensure_root_logging_configured()
    mcp.run()


if __name__ == "__main__":
    main()
