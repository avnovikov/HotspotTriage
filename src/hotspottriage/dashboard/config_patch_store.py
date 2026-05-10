"""Dashboard YAML overlay and merged config snapshot for the UI and cache jobs."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from hotspottriage import config as _config
from hotspottriage import normalize as _normalize
from hotspottriage import score as _score_mod
from hotspottriage.dashboard.local_state import DEFAULT_SCORE_METRICS
from hotspottriage.username_privacy import redact_usernames_in_text


def merge_config_overlay(
    base_doc: dict[str, Any],
    patch_doc: dict[str, Any],
    key: str,
) -> dict[str, Any]:
    """Deep-merge ``patch_doc[key]`` into the corresponding section of ``base_doc``."""
    patch_chunk = patch_doc.get(key)
    if not isinstance(patch_chunk, dict):
        return deepcopy(base_doc.get(key) or {})
    base_chunk = base_doc.get(key)
    if isinstance(base_chunk, dict):
        return _config._deep_merge(deepcopy(base_chunk), patch_chunk)
    return deepcopy(patch_chunk)


class ConfigPatchStore:
    """Base dashboard snapshot plus ``dashboard_config_patch.yml`` read/write and merge."""

    def __init__(self, base_snapshot: dict[str, Any], patch_path: Path) -> None:
        self._base = base_snapshot
        self._patch_path = patch_path

    @property
    def patch_path(self) -> Path:
        return self._patch_path

    def ensure_defaults(self) -> None:
        snap = self._base
        if not isinstance(snap.get("metric_normalization"), dict):
            snap["metric_normalization"] = deepcopy(_config.DEFAULTS["metric_normalization"])
        if not isinstance(snap.get("score_aggregation"), dict):
            snap["score_aggregation"] = deepcopy(_config.DEFAULTS["score_aggregation"])

    def load_patch_unlocked(self) -> dict[str, Any]:
        path = self._patch_path
        if not path.exists():
            return {}
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return {}
        if not text.strip():
            return {}
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError:
            return {}
        return data if isinstance(data, dict) else {}

    def write_patch_unlocked(self, data: dict[str, Any]) -> None:
        self._patch_path.parent.mkdir(parents=True, exist_ok=True)
        self._patch_path.write_text(
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

    def merged_snapshot(self) -> dict[str, Any]:
        """Base dashboard snapshot merged with persisted YAML overlay."""
        out = deepcopy(self._base)
        patch = self.load_patch_unlocked()
        for key in ("metric_normalization", "score_aggregation", "proposed_models"):
            sub = patch.get(key)
            if isinstance(sub, dict):
                base_chunk = out.get(key)
                if isinstance(base_chunk, dict):
                    out[key] = _config._deep_merge(base_chunk, sub)
                else:
                    out[key] = deepcopy(sub)
        return out

    def score_metrics_csv_for_cache_jobs(self) -> str:
        """Comma-separated product metrics from merged snapshot (not the UI)."""
        snap = self.merged_snapshot()
        raw = snap.get("score_metrics")
        if isinstance(raw, list) and raw:
            parts = [str(x).strip() for x in raw if str(x).strip()]
            if parts:
                return ",".join(parts)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        return DEFAULT_SCORE_METRICS

    def validate_merged_patch(self, merged_patch: dict[str, Any]) -> None:
        """Raise ``ValueError`` if overlay produces invalid normalization/score config."""
        probe = deepcopy(_config.DEFAULTS)
        for key in ("metric_normalization", "score_aggregation", "proposed_models"):
            probe[key] = merge_config_overlay(self._base, merged_patch, key)
        _normalize.validate_metric_normalization(probe)
        _score_mod.validate_score_aggregation(probe)
        _config._validate_proposed_models(probe)

    def enrich_snapshot_for_ui(self, snap: dict[str, Any]) -> dict[str, Any]:
        """Add ``*_display`` strings for dashboard UI; canonical paths unchanged."""
        out = deepcopy(snap)
        proj = out.get("project")
        if isinstance(proj, dict):
            p = str(proj.get("path") or "").strip()
            if p:
                proj["path_display"] = redact_usernames_in_text(p)
        dash = out.get("dashboard")
        if isinstance(dash, dict):
            dt = str(dash.get("default_target") or "").strip()
            if dt:
                dash["default_target_display"] = redact_usernames_in_text(dt)
        return out
