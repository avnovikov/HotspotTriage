"""Merge MCP ``analyze`` tool arguments into an analysis config dict."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from hotspottriage import config as ht_config
from hotspottriage import discovery


def effective_similarity_enabled_for_mcp_analyze(
    similarity: bool | None,
    path_filter: str | None,
) -> bool:
    """Resolve DeepCSIM default for MCP ``analyze``: off when *path_filter* is set.

    Omitted ``similarity`` (``None``) uses ``False`` for non-empty *path_filter*
    (scoped agent triage) and ``True`` for whole-repo runs. An explicit
    ``True``/``False`` always wins.
    """
    if similarity is not None:
        return bool(similarity)
    ft = path_filter.strip() if isinstance(path_filter, str) else ""
    return False if ft else True


def build_analyze_config(
    target: str,
    path_filter: str | None = None,
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
    cfg = deepcopy(ht_config.DEFAULTS)
    if not discovery.is_git_url(target):
        local_target = Path(target).expanduser()
        if local_target.is_dir():
            cfg = ht_config.load_analyze_config_for_local_repo(local_target.resolve())

    if path_filter:
        cfg["filter"] = [f.strip() for f in path_filter.split(",")]

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
        cfg = ht_config._deep_merge(cfg, config_overrides)
        if path_filter:
            cfg["filter"] = [f.strip() for f in path_filter.split(",")]
        if score_metrics:
            cfg["score_metrics"] = [m.strip() for m in score_metrics.split(",")]

    return cfg
