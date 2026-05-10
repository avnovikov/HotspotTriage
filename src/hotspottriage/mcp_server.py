"""FastMCP server for HotspotTriage.

Exposes analyze and init_config as MCP tools for Claude and other AI assistants.

Usage (stdio MCP server):
    hotspottriage start-mcp-server [--open-browser] [--default-target /path/to/repo]
    hotspottriage-mcp                # legacy console_scripts alias
"""
from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
import json
import logging
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from hotspottriage import cache as _cache
from hotspottriage import cache_generator as _cache_gen
from hotspottriage import config as _config
from hotspottriage.dashboard.log_handler import MemoryLogHandler
from hotspottriage.dashboard.server import DashboardServer
from hotspottriage.dashboard.stats import StatsCollector
from hotspottriage import discovery, stats
from hotspottriage import revision_cache as _rev_cache
from hotspottriage.mcp.analyze_args import resolve_analyze_inputs
from hotspottriage.mcp.analyze_metadata import build_analyze_metadata
from hotspottriage.mcp.analyze_orchestration import run_live_analysis, run_snapshot_compare
from hotspottriage.mcp.analyze_request import AnalyzeRequest
from hotspottriage.mcp.analyze_summary import build_mcp_analyze_summary
from hotspottriage.mcp.block_result_serialization import block_analysis_results_as_dicts
from hotspottriage.mcp.block_row_utils import synthetic_block_row_dicts as _synthetic_block_row_dicts
from hotspottriage.mcp.cache_warmup import initialize_repository_cache
from hotspottriage.mcp.dashboard_publish import (
    publish_block_metrics_to_dashboard,
    publish_manager_rows_to_dashboard,
)
from hotspottriage.mcp.errors import mcp_classify_exception as _mcp_classify_exception
from hotspottriage.mcp.errors import mcp_tool_error as _mcp_tool_error
from hotspottriage.mcp.init_paths import paths_written_as_str_list
from hotspottriage.mcp.local_target import local_repo_path_or_error
from hotspottriage.mcp.repo_filter import build_repo_keep_predicate as _build_repo_keep_predicate
from hotspottriage.mcp.target import resolve_mcp_target as _resolve_mcp_target_impl
from hotspottriage.path_utils import resolve_local_repo_path
from hotspottriage.username_privacy import UsernameRedactingFormatter

logger = logging.getLogger(__name__)

# Populated in :func:`main` before ``mcp.run()`` (used by dashboard lifespan).
_mcp_dashboard_cli: argparse.Namespace | None = None
# Optional default repo for MCP tools when ``target`` is omitted or empty.
_mcp_default_target: str | None = None
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
    UsernameRedactingFormatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
)
if _dashboard_log_handler not in logging.getLogger().handlers:
    logging.getLogger().addHandler(_dashboard_log_handler)


def _get_dashboard_instance() -> DashboardServer | None:
    """Return the live dashboard instance (or ``None`` if disabled)."""
    return _dashboard_server_instance


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


def get_mcp_default_target() -> str | None:
    """Return ``--default-target`` from server argv, or ``None`` if unset / before :func:`main`."""
    return _mcp_default_target


def _resolve_mcp_target(target: str) -> str:
    """Resolve repo path/URL: explicit ``target``, else ``--default-target``, else error."""
    return _resolve_mcp_target_impl(target, default_target=_mcp_default_target)


def _effective_dashboard_config() -> dict[str, Any]:
    """Layered YAML (global + ``<cwd>/.hotspottriage/``) plus MCP CLI dashboard flags."""
    cfg = _config.load_config(Path.cwd())
    cli = get_mcp_dashboard_cli_args()
    if cli is not None:
        cfg = _config.apply_mcp_dashboard_cli_overrides(
            cfg,
            no_dashboard=bool(cli.no_dashboard),
            dashboard_port=cli.dashboard_port,
            dashboard_host=cli.dashboard_host,
            open_browser=bool(cli.open_browser),
        )
    dt = get_mcp_default_target()
    if dt:
        dash = dict(cfg.get("dashboard") or {})
        dash["default_target"] = dt
        cfg["dashboard"] = dash
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
                config=_config.to_dashboard_snapshot(
                    cfg,
                    project_path=str(Path.cwd().resolve()),
                ),
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
    parser.add_argument(
        "--default-target",
        type=str,
        default=None,
        metavar="PATH_OR_URL",
        help=(
            "Default repo path or git URL for MCP tools when target is omitted or blank "
            "(analyze, generate_cache, cache_status, clear_cache; project init_config)."
        ),
    )
    args, rest = parser.parse_known_args()
    sys.argv = [sys.argv[0], *rest]
    return args


def _format_block_analysis_payload(
    analysis_root: str,
    cfg: dict[str, Any],
    results_full: list[stats.Statistic],
    *,
    compact: bool,
    progress_callback: Callable[[str, int, int], None] | None,
    deltas: dict[str, Any] | None = None,
    head_sha: str | None = None,
    git_repo: Path | None = None,
    snapshot_commit_full: str | None = None,
    include_summary: bool = False,
) -> dict[str, Any]:
    """Publish + limit + cache + optional compact rows (shared MCP analyze path)."""
    publish_block_metrics_to_dashboard(
        analysis_root,
        results_full,
        cfg,
        get_dashboard_instance=_get_dashboard_instance,
    )
    results = stats.sort_and_limit(results_full, by=cfg["sort"], limit=cfg["limit"])

    cache_info = initialize_repository_cache(
        analysis_root,
        cfg,
        get_cache_manager=_get_cache_manager,
        progress_callback=progress_callback,
    )
    publish_manager_rows_to_dashboard(
        analysis_root,
        cfg,
        get_dashboard_instance=_get_dashboard_instance,
        get_cache_manager=_get_cache_manager,
        build_keep_predicate=_build_repo_keep_predicate,
        synthetic_block_rows=_synthetic_block_row_dicts(results_full),
    )

    results_list = block_analysis_results_as_dicts(
        results, compact=compact, merged_config=cfg
    )
    metadata = build_analyze_metadata(
        cfg,
        analysis_root,
        results_full,
        results,
        git_repo=git_repo,
        snapshot_commit_full=snapshot_commit_full,
    )

    out: dict[str, Any] = {
        "metadata": metadata,
        "results": results_list,
        "cache": cache_info,
    }
    if include_summary:
        out["summary"] = build_mcp_analyze_summary(results_full)
    if deltas is not None:
        out["deltas"] = deltas
    if head_sha is not None:
        out["head_sha"] = head_sha
    return out


def _run_cached_block_analysis_impl(req: AnalyzeRequest) -> dict[str, Any]:
    """Run cache-backed block analysis from a typed :class:`AnalyzeRequest`."""
    inputs = resolve_analyze_inputs(
        req.target,
        path_filter=req.path_filter,
        score_metrics=req.score_metrics,
        limit=req.limit,
        since=req.since,
        until=req.until,
        respect_gitignore=req.respect_gitignore,
        ignore_dir=req.ignore_dir,
        similarity=req.similarity,
        compact=req.compact,
        sort=req.sort,
        config_overrides=req.config_overrides,
        before_sha=req.before_sha,
        after_sha=req.after_sha,
        include_summary=req.include_summary,
    )

    if inputs.before_sha and inputs.after_sha:
        after_rows, deltas, after_resolved = run_snapshot_compare(inputs)
        return _format_block_analysis_payload(
            str(inputs.local_repo),
            inputs.cfg,
            after_rows,
            compact=inputs.compact,
            progress_callback=req.progress_callback,
            deltas=deltas,
            head_sha=after_resolved,
            git_repo=inputs.local_repo,
            snapshot_commit_full=after_resolved,
            include_summary=inputs.include_summary,
        )

    results_full, head_sha_val, deltas = run_live_analysis(
        inputs,
        get_cache_manager=_get_cache_manager,
        progress_callback=req.progress_callback,
    )

    return _format_block_analysis_payload(
        inputs.analysis_root,
        inputs.cfg,
        results_full,
        compact=inputs.compact,
        progress_callback=req.progress_callback,
        deltas=deltas,
        head_sha=head_sha_val,
        git_repo=inputs.local_repo,
        snapshot_commit_full=None,
        include_summary=inputs.include_summary,
    )


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
    similarity: bool | None = None,
    compact: bool = True,
    sort: str = "score",
    progress_callback: Callable[[str, int, int], None] | None = None,
    config_overrides: dict[str, Any] | None = None,
    before_sha: str | None = None,
    after_sha: str | None = None,
    include_summary: bool = False,
) -> dict[str, Any]:
    """Block-level analysis + cache warm-up; returns dict with ``metadata``, ``results``, ``cache`` (not JSON).

    Optional ``progress_callback(label, done, total)`` mirrors
    :func:`hotspottriage.stats.build_block_stats` progress events.

    Local repositories record a **revision snapshot** on each successful analyze
    (``revisions.pkl``).  ``before_sha`` / ``after_sha`` compare cached snapshots
    only — HotspotTriage never checks out another revision.
    """
    req = AnalyzeRequest.from_tool_kwargs(
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
        progress_callback=progress_callback,
        config_overrides=config_overrides,
        before_sha=before_sha,
        after_sha=after_sha,
        include_summary=include_summary,
    )
    return _run_cached_block_analysis_impl(req)


@mcp.tool()
def analyze(
    target: str = "",
    filter: str | None = None,
    score_metrics: str | None = None,
    limit: int | None = None,
    sort: str = "score",
    since: str | None = None,
    until: str | None = None,
    respect_gitignore: bool = True,
    ignore_dir: str | None = None,
    similarity: bool | None = None,
    compact: bool = True,
    before_sha: str | None = None,
    after_sha: str | None = None,
    include_summary: bool = False,
) -> str:
    """Analyze a repository: block-level metrics, disk cache, and dashboard publish.

    Always runs the cache-backed block pipeline. Returns JSON with a top-level
    ``metadata`` object (provenance: git head/branch, timestamps, filter list,
    row counts, config fingerprint), ``results``, ``cache``, optional ``head_sha``
    (full commit recorded for revision snapshots on local repos), and optional
    ``deltas`` when
    ``before_sha`` is set (or when both ``before_sha`` and ``after_sha`` select
    cached snapshots only).
    By default each result row is compact (function, score, bands, model, and
    narrative fields); set ``compact`` to false for full metric dicts.

    Args:
        target: Path to a local git repo or remote git URL. Empty uses ``--default-target``
            from ``hotspottriage start-mcp-server`` if set.
        filter: Comma-separated tokens, matched against repo-relative POSIX paths
            (forward slashes; no leading ``./``). Behaviour depends on the tokens:

            **Literal path list (OR):** When there are **two or more** tokens and **every**
            token is a concrete path (no ``* ? [ ] { }`` glob characters), a file is kept
            if it equals **any** token after normalisation — OR semantics.

            **Glob mode (AND):** Otherwise (a single token, any token contains glob
            characters, or a mix of literals and globs), tokens use gitignore-style
            matching and a file must satisfy **all** patterns (``!`` negates one
            pattern). The implicit ``default_filter`` is appended unless disabled in
            config. Example: ``**/dashboard/*.py`` matches dashboard dirs at any depth;
            ``src/**,!**/test_*`` includes ``src`` but excludes ``test_*`` paths.

            **CLI / cache-generator note:** The ``hotspottriage`` CLI and
            ``generate_cache`` always use glob AND mode; the OR shortcut exists only
            for this MCP ``analyze`` path (``build_repo_keep_predicate`` in ``mcp.repo_filter``).
        score_metrics: Comma-separated metrics for scoring (default: churn_per_sloc,cyclomatic)
        limit: Maximum number of block rows returned
        sort: 'score' (default) or 'file'
        since: Git --since date filter
        until: Git --until date filter
        respect_gitignore: Apply .gitignore rules (default: true)
        ignore_dir: Comma-separated directory prefixes to skip
        similarity: DeepCSIM similarity per block. When omitted: ``False`` if
            ``filter`` is set (fast scoped triage), ``True`` for whole-repo runs.
            Pass ``True`` or ``False`` explicitly to override.
        compact: When true (default), each row includes ``file``, ``function``,
            ``score``, ``risk_band``, ``proposed_model``, ``score_driver``, and
            ``rationale`` (short natural-language summary for agents). Use
            ``compact=false`` for full metrics, ``score_explanation``, and
            multi-line ``score_narrative``.
        before_sha: Optional commit (SHA, branch, ``HEAD~1``, …) to diff **against**.
            Must already have been recorded by a prior ``analyze`` at that checkout
            (use the returned ``head_sha``). With **only** ``before_sha``: runs live
            analysis at the current ``target`` HEAD, records that snapshot, and adds
            ``deltas`` vs the cached ``before_sha`` snapshot. Local repos only.
        after_sha: Optional second commit; requires ``before_sha``. When both are set,
            returns cached results for ``after_sha`` plus ``deltas`` vs ``before_sha``
            **without** running a new analysis (both snapshots must exist). Cannot be
            used without ``before_sha``.
        include_summary: When ``True``, add a ``summary`` object with aggregates
            (**block_count**, risk counts, sums, max cyclomatic/score, **mean_score**)
            computed from the **full** pre-``limit`` result set. Default ``False``
            keeps the response shape unchanged for callers that do not need it.

    Returns:
        JSON object with ``metadata``, ``results``, and ``cache``; optional
        ``summary`` when ``include_summary`` is true; optional ``head_sha`` for local
        targets; optional ``deltas`` when ``before_sha`` is set; or an ``error``
        object ``{"code", "message", "details"}`` on failure
    """
    try:
        resolved = _resolve_mcp_target(target)
    except ValueError as e:
        return _mcp_tool_error("INVALID_TARGET", str(e))
    try:
        req = AnalyzeRequest.from_tool_kwargs(
            resolved,
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
            before_sha=before_sha,
            after_sha=after_sha,
            include_summary=include_summary,
        )
        response = _run_cached_block_analysis_impl(req)
        return json.dumps(response, indent=2)
    except Exception as e:
        logger.exception("Cache-backed analysis failed")
        code, err_msg, det = _mcp_classify_exception(e)
        return _mcp_tool_error(code, err_msg, details=det)


@mcp.tool()
def cache_status(target: str = "") -> str:
    """Check cache status and statistics for a repository.

    Args:
        target: Path to a local git repo. Empty uses ``--default-target`` if set.

    Returns:
        JSON with cache statistics (size, entries, age)
    """
    try:
        raw = _resolve_mcp_target(target).strip()
        repo_or_err = local_repo_path_or_error(
            raw,
            tool="cache_status",
            remote_message=(
                "cache_status requires a local repository path, not a remote URL"
            ),
        )
        if isinstance(repo_or_err, str):
            return repo_or_err
        repo_path = repo_or_err
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

    except ValueError as e:
        code, err_msg, det = _mcp_classify_exception(e)
        return _mcp_tool_error(code, err_msg, details=det)
    except Exception as e:
        logger.exception("Cache status check failed")
        code, err_msg, det = _mcp_classify_exception(e)
        return _mcp_tool_error(code, err_msg, details=det)


@mcp.tool()
def clear_cache(target: str = "") -> str:
    """Clear the block-level cache and revision snapshot store for a repository.

    Removes ``blocks.pkl`` and ``revisions.pkl`` under
    ``<repo>/.hotspottriage/cache/`` when present.

    Args:
        target: Path to a local git repo. Empty uses ``--default-target`` if set.

    Returns:
        Status message
    """
    try:
        raw = _resolve_mcp_target(target).strip()
        repo_or_err = local_repo_path_or_error(
            raw,
            tool="clear_cache",
            remote_message=(
                "clear_cache requires a local repository path, not a remote URL"
            ),
        )
        if isinstance(repo_or_err, str):
            return repo_or_err
        repo_path = repo_or_err
        cache_dir = _cache.cache_path_for(repo_path)

        if not cache_dir.exists():
            return json.dumps({
                "status": "success",
                "message": "No cache to clear",
            })

        cache_file = cache_dir / _cache._CACHE_FILE
        if cache_file.exists():
            cache_file.unlink()

        rev_file = _rev_cache.revisions_cache_path(repo_path)
        if rev_file.exists():
            rev_file.unlink()

        # Remove directory if empty
        try:
            cache_dir.rmdir()
        except OSError:
            pass  # Directory not empty, that's ok

        return json.dumps({
            "status": "success",
            "message": f"Cleared cache in {cache_dir}",
        })

    except ValueError as e:
        code, err_msg, det = _mcp_classify_exception(e)
        return _mcp_tool_error(code, err_msg, details=det)
    except Exception as e:
        logger.exception("Cache clear failed")
        code, err_msg, det = _mcp_classify_exception(e)
        return _mcp_tool_error(code, err_msg, details=det)


@mcp.tool()
def generate_cache(
    target: str = "",
    filter: str | None = None,
    score_metrics: str = "churn_per_sloc,cyclomatic",
) -> str:
    """Generate comprehensive codebase cache (blocks + classes/methods).

    Creates a complete snapshot including block-level metrics with churn data
    and class/method structure analysis. Results are cached in
    <repo>/.hotspottriage/cache/blocks.pkl.

    Args:
        target: Path to a local git repo. Empty uses ``--default-target`` if set.
        filter: Comma-separated gitignore-style patterns (AND with each other and the
            default filter; ``!`` negates). No MCP literal-path OR shortcut — same as
            the ``hotspottriage-cache`` CLI.
        score_metrics: Metrics to compute score from (default: churn_per_sloc,cyclomatic)

    Returns:
        JSON with complete cache including blocks, classes, and status
    """
    try:
        resolved = _resolve_mcp_target(target)
        cache_data = _cache_gen.generate_full_cache(
            target=resolved,
            filter=filter,
            score_metrics=score_metrics,
            verbose=False,
        )
        return json.dumps(cache_data, indent=2)
    except ValueError as e:
        code, err_msg, det = _mcp_classify_exception(e)
        return _mcp_tool_error(code, err_msg, details=det)
    except Exception as e:
        logger.exception("Cache generation failed")
        code, err_msg, det = _mcp_classify_exception(e)
        return _mcp_tool_error(code, err_msg, details=det)


@mcp.tool()
def init_config(target: str = "", is_global: bool = False) -> str:
    """Initialize HotspotTriage configuration files.

    Args:
        target: Path to git repository (empty/unused if is_global=True). For project scope,
            empty uses ``--default-target`` if set, otherwise ``.``.
        is_global: Initialize global config (~/.hotspottriage/) instead of project config

    Returns:
        Status message with list of files created
    """
    try:
        if is_global:
            written = _config.init_config(scope="global")
            files = paths_written_as_str_list(written)
            return json.dumps({
                "status": "success",
                "message": f"Initialized global config",
                "files": files,
            })
        else:
            t = (target or "").strip()
            if not t:
                t = (_mcp_default_target or ".").strip()
            repo_or_err = local_repo_path_or_error(
                t,
                tool="init_config",
                remote_message=(
                    "init_config (project scope) requires a local repository path, "
                    "not a remote URL"
                ),
            )
            if isinstance(repo_or_err, str):
                return repo_or_err
            repo_path = repo_or_err
            written = _config.init_config(scope="project", target=repo_path)
            files = paths_written_as_str_list(written)
            return json.dumps({
                "status": "success",
                "message": f"Initialized project config in {repo_path / _config.PROJECT_CONFIG_DIRNAME}",
                "files": files,
            })

    except Exception as e:
        logger.exception("Config init failed")
        code, err_msg, det = _mcp_classify_exception(e)
        return _mcp_tool_error(code, err_msg, details=det)


def main() -> None:
    """Entry point for the FastMCP server."""
    global _mcp_dashboard_cli, _mcp_default_target
    _mcp_dashboard_cli = _parse_mcp_dashboard_argv()
    dt = getattr(_mcp_dashboard_cli, "default_target", None)
    _mcp_default_target = dt.strip() if isinstance(dt, str) and dt.strip() else None
    _ensure_root_logging_configured()
    mcp.run()


if __name__ == "__main__":
    main()
