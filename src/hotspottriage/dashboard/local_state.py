"""Persisted ``dashboard_state.json`` for the dashboard cache UI."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from hotspottriage.dashboard.cache_filter_fields import (
    compose_filter_from_fields,
    split_filter_for_fields,
)
from hotspottriage.username_privacy import redact_usernames_in_text

DEFAULT_SCORE_METRICS = "churn_per_sloc,cyclomatic"


class DashboardLocalState:
    """Read/write ``last_target`` / filter fields / ``recent_targets`` under a lock."""

    def __init__(
        self,
        state_file: Path,
        state_lock: threading.Lock,
        *,
        default_score_metrics: str = DEFAULT_SCORE_METRICS,
    ) -> None:
        self._state_file = state_file
        self._lock = state_lock
        self._default_score_metrics = default_score_metrics

    @property
    def lock(self) -> threading.Lock:
        return self._lock

    def _empty(self) -> dict[str, Any]:
        return {
            "last_target": "",
            "last_filter": "",
            "last_include": "",
            "last_exclude": "",
            "last_score_metrics": self._default_score_metrics,
            "recent_targets": [],
        }

    def load_unlocked(self) -> dict[str, Any]:
        empty = self._empty()
        if not self._state_file.exists():
            return empty
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return empty
            merged = {**empty, **data}
            lf = str(merged.get("last_filter", "")).strip()
            li = str(merged.get("last_include", "")).strip()
            le = str(merged.get("last_exclude", "")).strip()
            if lf and not li and not le:
                merged["last_include"], merged["last_exclude"] = split_filter_for_fields(lf)
            elif (li or le) and not lf:
                merged["last_filter"] = compose_filter_from_fields(li, le) or ""
            return merged
        except Exception:
            return empty

    def load(self) -> dict[str, Any]:
        with self._lock:
            return self.load_unlocked()

    def save(self, updates: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            base = self.load_unlocked()
            merged = {**base, **updates}
            tgt = str(merged.get("last_target", "")).strip()
            rec = [str(x) for x in (merged.get("recent_targets") or []) if str(x).strip()]
            if tgt:
                rec = [t for t in rec if t != tgt]
                rec.insert(0, tgt)
                rec = rec[:15]
            merged["recent_targets"] = rec
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            self._state_file.write_text(json.dumps(merged, indent=2), encoding="utf-8")
            return merged

    def enrich_cache_context_for_response(self, state: dict[str, Any]) -> dict[str, Any]:
        """Add UI-only redacted path fields; ``last_target`` on disk stays canonical."""
        out = dict(state)
        lt = str(out.get("last_target", "") or "").strip()
        out["last_target_display"] = redact_usernames_in_text(lt) if lt else ""
        rec = out.get("recent_targets")
        if isinstance(rec, list):
            out["recent_targets_display"] = [
                redact_usernames_in_text(str(x)) for x in rec if str(x).strip()
            ]
        else:
            out["recent_targets_display"] = []
        return out

    def persist_cache_analysis_prefs(
        self,
        *,
        target: str,
        filt: str | None,
        include: str,
        exclude: str,
        last_score_metrics: str,
    ) -> None:
        filt_str = "" if filt is None else str(filt).strip()
        self.save(
            {
                "last_target": target,
                "last_filter": filt_str,
                "last_include": str(include).strip(),
                "last_exclude": str(exclude).strip(),
                "last_score_metrics": last_score_metrics,
            }
        )
