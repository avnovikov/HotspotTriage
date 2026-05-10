"""In-memory block metric rows for heatmap, histograms, and lazy narratives."""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from hotspottriage import cache as _cache
from hotspottriage import config as _config
from hotspottriage import stats as _stats_mod
from hotspottriage.discovery import is_git_url

logger = logging.getLogger(__name__)


class BlockMetricsStore:
    """Thread-safe store of scored block dicts; optional analysis repo for config parity."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rows: list[dict[str, Any]] = []
        self._analysis_repo: Path | None = None

    def read_rows(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._rows)

    @property
    def lock(self):
        return self._lock

    def full_analyze_config_for_scoring(self) -> dict[str, Any]:
        """Merged config for block scoring / explanations (CLI + MCP parity)."""
        root = (
            self._analysis_repo
            if self._analysis_repo is not None
            else Path.cwd().resolve()
        )
        return _config.load_analyze_config_for_local_repo(root)

    def derive_block_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Score raw block rows using the same merged config as CLI / MCP analyze."""
        merged = self.full_analyze_config_for_scoring()
        scored_rows: list[dict[str, Any]] = []
        raw_metric_keys = {
            "path",
            "sloc",
            "normalized_sloc",
            "cyclomatic",
            "halstead",
            "maintainability",
            "churn",
            "churn_per_sloc",
            "decayed_churn",
            "decayed_churn_per_sloc",
            "smell_count",
            "smell_severity",
            "smell_burden",
            "similarity_score",
            "match_count",
        }
        for row in rows:
            if not isinstance(row, dict):
                continue
            if raw_metric_keys <= set(row):
                scored_rows.extend(
                    _stats_mod.derive_block_score_rows(
                        [row],
                        merged,
                        score_metrics=list(merged.get("score_metrics") or []),
                        smell_weight=float(merged.get("smell_weight", 0.0)),
                        similarity_enabled=bool(merged.get("similarity_enabled", True)),
                    )
                )
            else:
                scored_rows.append(dict(row))
        return scored_rows

    def publish(
        self,
        rows: list[dict[str, Any]],
        *,
        analysis_repo: Path | None = None,
    ) -> None:
        """Replace stored rows used by distribution histograms and heatmap."""
        if analysis_repo is not None:
            p = Path(analysis_repo).expanduser().resolve()
            if p.is_dir():
                self._analysis_repo = p
        scored_rows = self.derive_block_rows(rows)
        with self._lock:
            self._rows = scored_rows

    def analysis_config_overrides(self, *, target: str | None = None) -> dict[str, Any]:
        """Return MN/SA overrides for cache generation (same repo layers as MCP analyze)."""
        from copy import deepcopy

        if target and not is_git_url(target):
            cand = Path(target).expanduser().resolve()
            root = cand if cand.is_dir() else (
                self._analysis_repo or Path.cwd().resolve()
            )
        else:
            root = self._analysis_repo or Path.cwd().resolve()
        full = _config.load_analyze_config_for_local_repo(root)
        overrides: dict[str, Any] = {}
        for key in ("metric_normalization", "score_aggregation"):
            value = full.get(key)
            if isinstance(value, dict):
                overrides[key] = deepcopy(value)
        return overrides

    def hydrate_when_missing(self, repo: Path, *, cache_file_exists: bool) -> bool:
        """Populate rows from MCP cache manager or disk when memory is empty."""
        with self._lock:
            has_rows = bool(self._rows)
        if not has_rows:
            try:
                # Lazy import avoids import-time cycle with mcp_server (which imports DashboardServer).
                from hotspottriage.mcp_server import _get_cache_manager  # noqa: PLC0415

                mgr = _get_cache_manager(repo)
                live_rows = mgr.get_all_rows()
                if live_rows:
                    self.publish(live_rows, analysis_repo=repo)
                    has_rows = True
            except Exception:
                logger.debug(
                    "Hydrating block metrics from MCP cache skipped",
                    exc_info=True,
                )
        if cache_file_exists and not has_rows:
            loaded_rows = _cache.load_block_results(repo)
            if loaded_rows:
                self.publish(loaded_rows, analysis_repo=repo)
                has_rows = True
        return has_rows
