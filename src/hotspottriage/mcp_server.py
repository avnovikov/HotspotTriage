"""FastMCP server for HotspotTriage.

Exposes analyze and init_config as MCP tools for Claude and other AI assistants.

Usage (stdio MCP server):
    hotspottriage start-mcp-server [--open-browser] [--default-target /path/to/repo]
    hotspottriage-mcp                # legacy console_scripts alias
"""
from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import logging
import math
import subprocess
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
from hotspottriage import discovery, filtering, explain as _explain, output as _output, stats
from hotspottriage import revision_cache as _rev_cache
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
    t = target.strip() if isinstance(target, str) else ""
    if t:
        return t
    if _mcp_default_target:
        return _mcp_default_target
    raise ValueError(
        "MCP tool requires a non-empty target (local git repo path or remote URL), "
        "or start the server with --default-target PATH_OR_URL"
    )


def _effective_similarity_enabled_for_mcp_analyze(
    similarity: bool | None,
    filter: str | None,
) -> bool:
    """Resolve DeepCSIM default for MCP ``analyze``: off when *filter* is set.

    Omitted ``similarity`` (``None``) uses ``False`` for non-empty *filter*
    (scoped agent triage) and ``True`` for whole-repo runs. An explicit
    ``True``/``False`` always wins.
    """
    if similarity is not None:
        return bool(similarity)
    ft = filter.strip() if isinstance(filter, str) else ""
    return False if ft else True


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


def _is_block_row_for_delta(row: stats.Statistic) -> bool:
    p = str(row.path)
    if "::" not in p:
        return False
    if p.split("::", 1)[0].startswith("__"):
        return False
    return str(row.score_band).lower() != "aggregate"


def _metric_triplet(
    before: int | float | None, after: int | float | None
) -> dict[str, int | float | None]:
    if before is None and after is None:
        return {"before": None, "after": None, "delta": None}
    if before is None:
        return {"before": None, "after": after, "delta": None}
    if after is None:
        return {"before": before, "after": None, "delta": None}
    delta = after - before
    return {"before": before, "after": after, "delta": delta}


def _rows_equal_raw(a: stats.Statistic, b: stats.Statistic) -> bool:
    for name in ("cyclomatic", "sloc", "halstead", "churn", "smell_count"):
        if getattr(a, name) != getattr(b, name):
            return False
    for name in ("churn_per_sloc", "decayed_churn", "decayed_churn_per_sloc"):
        if not math.isclose(
            float(getattr(a, name)),
            float(getattr(b, name)),
            rel_tol=0.0,
            abs_tol=1e-6,
        ):
            return False
    return True


def _build_block_delta_report(
    head_rows: list[stats.Statistic],
    base_rows: list[stats.Statistic],
) -> dict[str, Any]:
    """Compare block rows at HEAD vs a baseline revision (raw metrics + score snapshot)."""
    head_map = {r.path: r for r in head_rows if _is_block_row_for_delta(r)}
    base_map = {r.path: r for r in base_rows if _is_block_row_for_delta(r)}
    all_paths = sorted(set(head_map) | set(base_map))
    by_block: list[dict[str, Any]] = []
    blocks_added = blocks_removed = blocks_modified = blocks_unchanged = 0
    total_cyclomatic_delta = 0
    total_sloc_delta = 0
    total_halstead_delta = 0
    total_churn_delta = 0
    total_smell_count_delta = 0

    for path in all_paths:
        h = head_map.get(path)
        b = base_map.get(path)
        if h and b:
            if _rows_equal_raw(h, b):
                blocks_unchanged += 1
                continue
            blocks_modified += 1
            status = "modified"
        elif h and not b:
            blocks_added += 1
            status = "added"
        else:
            blocks_removed += 1
            status = "removed"
            assert b is not None

        entry: dict[str, Any] = {"path": path, "status": status}
        for fname in ("cyclomatic", "sloc", "halstead", "churn", "smell_count"):
            bv = int(getattr(b, fname)) if b else None
            hv = int(getattr(h, fname)) if h else None
            entry[fname] = _metric_triplet(bv, hv)
        for fname in ("churn_per_sloc", "decayed_churn", "decayed_churn_per_sloc"):
            bv = float(getattr(b, fname)) if b else None
            hv = float(getattr(h, fname)) if h else None
            entry[fname] = _metric_triplet(bv, hv)
        entry["score"] = _metric_triplet(
            float(b.score) if b else None,
            float(h.score) if h else None,
        )
        by_block.append(entry)

        if status == "modified" and h and b:
            total_cyclomatic_delta += h.cyclomatic - b.cyclomatic
            total_sloc_delta += h.sloc - b.sloc
            total_halstead_delta += h.halstead - b.halstead
            total_churn_delta += h.churn - b.churn
            total_smell_count_delta += h.smell_count - b.smell_count
        elif status == "added" and h:
            total_cyclomatic_delta += h.cyclomatic
            total_sloc_delta += h.sloc
            total_halstead_delta += h.halstead
            total_churn_delta += h.churn
            total_smell_count_delta += h.smell_count
        elif status == "removed" and b:
            total_cyclomatic_delta -= b.cyclomatic
            total_sloc_delta -= b.sloc
            total_halstead_delta -= b.halstead
            total_churn_delta -= b.churn
            total_smell_count_delta -= b.smell_count

    return {
        "summary": {
            "blocks_added": blocks_added,
            "blocks_removed": blocks_removed,
            "blocks_modified": blocks_modified,
            "blocks_unchanged": blocks_unchanged,
            "total_cyclomatic_delta": total_cyclomatic_delta,
            "total_sloc_delta": total_sloc_delta,
            "total_halstead_delta": total_halstead_delta,
            "total_churn_delta": total_churn_delta,
            "total_smell_count_delta": total_smell_count_delta,
        },
        "by_block": by_block,
    }


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
    _publish_block_metrics_to_dashboard(analysis_root, results_full, cfg)
    results = stats.sort_and_limit(results_full, by=cfg["sort"], limit=cfg["limit"])

    cache_info = _initialize_repository(
        analysis_root, cfg, progress_callback=progress_callback
    )
    synthetic_block_rows = [
        r.as_dict()
        for r in results_full
        if str(r.path).split("::", 1)[0].startswith("__")
    ]
    _publish_manager_rows_to_dashboard(
        analysis_root, cfg, synthetic_block_rows=synthetic_block_rows
    )

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

    row_count = _normal_block_stat_count(results_full)
    truncated = _normal_block_stat_count(results) < row_count
    analyzed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    git_head: str | None = None
    git_branch: str | None = None
    if git_repo is not None and snapshot_commit_full:
        git_head = _git_short_object_name(git_repo, snapshot_commit_full)
        git_branch = "snapshot"
    elif git_repo is not None:
        git_head, git_branch = _git_live_head_and_branch(git_repo)

    metadata: dict[str, Any] = {
        "git_head": git_head,
        "git_branch": git_branch,
        "analyzed_at": analyzed_at,
        "target": analysis_root,
        "filter_applied": _effective_mcp_filter_patterns(cfg),
        "row_count": row_count,
        "truncated": truncated,
        "config_fingerprint": _config_fingerprint(cfg),
    }

    out: dict[str, Any] = {
        "metadata": metadata,
        "results": results_list,
        "cache": cache_info,
    }
    if include_summary:
        out["summary"] = _build_mcp_analyze_summary(results_full)
    if deltas is not None:
        out["deltas"] = deltas
    if head_sha is not None:
        out["head_sha"] = head_sha
    return out


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
    after_t = after_sha.strip() if isinstance(after_sha, str) else ""
    before_t = before_sha.strip() if isinstance(before_sha, str) else ""
    after_sha = after_t or None
    before_sha = before_t or None

    if after_sha and not before_sha:
        raise ValueError("after_sha requires before_sha")

    if (before_sha or after_sha) and discovery.is_git_url(target):
        raise ValueError(
            "before_sha and after_sha require a local git repository path, "
            "not a remote URL"
        )

    if discovery.is_git_url(target):
        config_target = target.strip()
        analysis_root = config_target
        local_repo: Path | None = None
    else:
        config_target = str(resolve_local_repo_path(target))
        analysis_root = config_target
        local_repo = Path(config_target)

    cfg = _build_analyze_config(
        config_target,
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
    cfg["similarity_enabled"] = _effective_similarity_enabled_for_mcp_analyze(
        similarity, filter
    )

    if before_sha and after_sha:
        assert local_repo is not None
        mgr = _rev_cache.RevisionCacheManager(local_repo)
        try:
            after_rows = mgr.get_snapshot_statistics(after_sha)
            before_rows = mgr.get_snapshot_statistics(before_sha)
        except _rev_cache.SnapshotNotFoundError as e:
            raise ValueError(str(e)) from e
        deltas = _build_block_delta_report(after_rows, before_rows)
        after_resolved = _rev_cache.resolve_commit_sha(local_repo, after_sha)
        return _format_block_analysis_payload(
            str(local_repo),
            cfg,
            after_rows,
            compact=compact,
            progress_callback=progress_callback,
            deltas=deltas,
            head_sha=after_resolved,
            git_repo=local_repo,
            snapshot_commit_full=after_resolved,
            include_summary=include_summary,
        )

    results_full = _analyze_repository(
        analysis_root,
        cfg,
        apply_limit=False,
        progress_callback=progress_callback,
    )
    head_sha_val: str | None = None
    if local_repo is not None:
        head_sha_val = _rev_cache.RevisionCacheManager(local_repo).record_snapshot(
            results_full
        )

    deltas: dict[str, Any] | None = None
    if before_sha:
        assert local_repo is not None
        mgr = _rev_cache.RevisionCacheManager(local_repo)
        try:
            before_rows = mgr.get_snapshot_statistics(before_sha)
        except _rev_cache.SnapshotNotFoundError as e:
            raise ValueError(str(e)) from e
        deltas = _build_block_delta_report(results_full, before_rows)

    return _format_block_analysis_payload(
        analysis_root,
        cfg,
        results_full,
        compact=compact,
        progress_callback=progress_callback,
        deltas=deltas,
        head_sha=head_sha_val,
        git_repo=local_repo,
        snapshot_commit_full=None,
        include_summary=include_summary,
    )


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
    similarity: bool | None = None,
    compact: bool = True,
    sort: str = "score",
    before_sha: str | None = None,
    after_sha: str | None = None,
    include_summary: bool = False,
) -> str:
    """Block-level analysis with disk cache warm-up; returns JSON with ``metadata``."""
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
            before_sha=before_sha,
            after_sha=after_sha,
            include_summary=include_summary,
        )
        return json.dumps(response, indent=2)

    except Exception as e:
        logger.exception("Cache-backed analysis failed")
        return json.dumps({"error": str(e)})


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
            for this MCP ``analyze`` path (``_build_repo_keep_predicate``).
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
        targets; optional ``deltas`` when ``before_sha`` is set; or ``{"error": ...}``
    """
    try:
        resolved = _resolve_mcp_target(target)
    except ValueError as e:
        return json.dumps({"error": str(e)})
    return _run_analyze_cached(
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
        if discovery.is_git_url(raw):
            return json.dumps({
                "status": "error",
                "message": "cache_status requires a local repository path, not a remote URL",
            })
        repo_path = resolve_local_repo_path(raw)
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
        return json.dumps({"status": "error", "message": str(e)})
    except Exception as e:
        logger.exception("Cache status check failed")
        return json.dumps({"status": "error", "message": str(e)})


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
        if discovery.is_git_url(raw):
            return json.dumps({
                "status": "error",
                "message": "clear_cache requires a local repository path, not a remote URL",
            })
        repo_path = resolve_local_repo_path(raw)
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
        return json.dumps({"status": "error", "message": str(e)})
    except Exception as e:
        logger.exception("Cache clear failed")
        return json.dumps({"status": "error", "message": str(e)})


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
        return json.dumps({"error": str(e)})
    except Exception as e:
        logger.exception("Cache generation failed")
        return json.dumps({"error": str(e)})


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
            # init_config currently returns a single Path for global scope.
            files = [str(written)] if isinstance(written, Path) else [str(f) for f in written]
            return json.dumps({
                "status": "success",
                "message": f"Initialized global config",
                "files": files,
            })
        else:
            t = (target or "").strip()
            if not t:
                t = (_mcp_default_target or ".").strip()
            repo_path = resolve_local_repo_path(t)
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
    """Build analysis config: local repos use ``load_config`` + dashboard patch
    (same as CLI analyze), then MCP tool arguments."""
    cfg = deepcopy(_config.DEFAULTS)
    if not discovery.is_git_url(target):
        local_target = Path(target).expanduser()
        if local_target.is_dir():
            cfg = _config.load_analyze_config_for_local_repo(local_target.resolve())

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
    return filtering.normalize_filter_pattern(path)


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


def _effective_mcp_filter_patterns(cfg: dict[str, Any]) -> list[str]:
    """Return the filter token list actually used by :func:`_build_repo_keep_predicate`."""
    raw_patterns = [p.strip() for p in cfg.get("filter", []) if p and str(p).strip()]
    use_literal_list = len(raw_patterns) > 1 and all(
        _is_literal_filter_path(p) for p in raw_patterns
    )
    if use_literal_list:
        return list(raw_patterns)
    patterns = list(raw_patterns)
    if not cfg.get("no_default_filter", False):
        df = cfg.get("default_filter")
        if isinstance(df, str) and df.strip():
            patterns.append(df.strip())
    return patterns


def _normal_block_stat_count(rows: list[stats.Statistic]) -> int:
    """Count non-synthetic block rows (exclude aggregate paths whose file starts with ``__``)."""
    return sum(
        1
        for r in rows
        if not str(r.path).split("::", 1)[0].startswith("__")
    )


def _non_synthetic_block_rows(rows: list[stats.Statistic]) -> list[stats.Statistic]:
    return [r for r in rows if not str(r.path).split("::", 1)[0].startswith("__")]


def _build_mcp_analyze_summary(rows: list[stats.Statistic]) -> dict[str, Any]:
    """Aggregate metrics over the full (pre-``limit``) block list for MCP ``include_summary``."""
    blocks = _non_synthetic_block_rows(rows)
    n = len(blocks)
    if n == 0:
        return {
            "block_count": 0,
            "high_risk_count": 0,
            "critical_risk_count": 0,
            "sum_cyclomatic": 0,
            "sum_sloc": 0,
            "max_cyclomatic": None,
            "max_score": None,
            "mean_score": 0.0,
        }
    high_risk_count = sum(1 for r in blocks if str(r.score_band).lower() == "high")
    critical_risk_count = sum(
        1 for r in blocks if str(r.score_band).lower() == "critical"
    )
    sum_cyclomatic = sum(int(r.cyclomatic) for r in blocks)
    sum_sloc = sum(int(r.sloc) for r in blocks)
    max_cyc = max(blocks, key=lambda r: int(r.cyclomatic))
    max_sc = max(blocks, key=lambda r: float(r.score))
    total_score = sum(float(r.score) for r in blocks)
    return {
        "block_count": n,
        "high_risk_count": high_risk_count,
        "critical_risk_count": critical_risk_count,
        "sum_cyclomatic": sum_cyclomatic,
        "sum_sloc": sum_sloc,
        "max_cyclomatic": {"path": max_cyc.path, "value": int(max_cyc.cyclomatic)},
        "max_score": {"path": max_sc.path, "value": round(float(max_sc.score), 4)},
        "mean_score": round(total_score / n, 4),
    }


def _config_fingerprint(cfg: dict[str, Any]) -> str:
    """Stable digest of the merged analyze config (for comparing runs)."""
    payload = json.dumps(cfg, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _git_short_object_name(repo: Path, full_sha: str) -> str | None:
    token = full_sha.strip()
    if not token:
        return None
    proc = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--short", f"{token}^{{commit}}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    lines = proc.stdout.strip().splitlines()
    return lines[0].strip() if lines else None


def _git_live_head_and_branch(repo: Path) -> tuple[str | None, str | None]:
    """Return ``(short HEAD sha, branch name or ``detached``)`` for a local repo."""
    proc = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None, None
    short_head = (proc.stdout.strip().splitlines() or [""])[0].strip() or None
    br = subprocess.run(
        ["git", "-C", str(repo), "branch", "--show-current"],
        check=False,
        capture_output=True,
        text=True,
    )
    branch = (br.stdout.strip().splitlines() or [""])[0].strip()
    if not branch:
        branch = "detached"
    return short_head, branch


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
    """One dict per row: file, symbol, score, band, model, driver, and a short agent rationale."""
    out: list[dict[str, Any]] = []
    for r in rows:
        p = r.path
        if granularity == "block" and "::" in p:
            file_path, fn = p.split("::", 1)
        else:
            file_path, fn = p, p
        score_band = str(r.score_band)
        out.append(
            {
                "file": file_path,
                "function": fn,
                "score": float(r.score),
                "risk_band": score_band,
                "proposed_model": _proposed_model_for_band(score_band, merged_config),
                "score_driver": r.score_driver,
                "rationale": _explain.compact_agent_rationale(
                    r, final_weights=r.score_final_weights
                ),
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
    target: str,
    rows: list[stats.Statistic],
    cfg: dict[str, Any],
) -> None:
    """Push raw block rows to the dashboard for heatmap/histogram endpoints."""
    if cfg.get("granularity") != "block":
        return
    dash = _dashboard_server_instance
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


def _block_metric_row_repo_file(path: str) -> str:
    """Repo-relative file path for a block metric row (strip ``::symbol``)."""
    file_key = path.split("::", 1)[0] if "::" in path else path
    return file_key.replace("\\", "/")


def _publish_manager_rows_to_dashboard(
    target: str,
    cfg: dict[str, Any],
    *,
    synthetic_block_rows: list[dict[str, Any]] | None = None,
) -> None:
    """Push cache-manager rows to the dashboard, scoped to *cfg* filters.

    Scoped block runs only replace cache entries for targeted files; older rows
    for other files remain in the manager. Publishing ``get_all_rows()`` without
    filtering would overwrite the dashboard and look like the filter was ignored.
    Synthetic rows (paths whose file segment starts with ``__``, e.g. similarity
    aggregate) are not persisted in the block cache; pass them via
    *synthetic_block_rows* so the dashboard stays aligned with the analysis run.
    Manager rows are filtered only with *keep* so stray synthetic keys in the
    pickle cannot override a similarity-disabled run.
    """
    dash = _dashboard_server_instance
    if dash is None:
        return
    try:
        with discovery.resolve_target(target) as repo:
            mgr = _get_cache_manager(repo)
            rows = mgr.get_all_rows()
            keep = _build_repo_keep_predicate(repo, cfg)
            merged: dict[str, dict[str, Any]] = {}
            for r in rows:
                if not isinstance(r, dict):
                    continue
                p = r.get("path")
                if not isinstance(p, str):
                    continue
                fk = _block_metric_row_repo_file(p)
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
    global _mcp_dashboard_cli, _mcp_default_target
    _mcp_dashboard_cli = _parse_mcp_dashboard_argv()
    dt = getattr(_mcp_dashboard_cli, "default_target", None)
    _mcp_default_target = dt.strip() if isinstance(dt, str) and dt.strip() else None
    _ensure_root_logging_configured()
    mcp.run()


if __name__ == "__main__":
    main()
