"""Batch smell burden normalization for file and block metric dicts."""
from __future__ import annotations

from typing import Any


def finalize_smell_burden(metrics_dicts: list[dict[str, Any]]) -> None:
    """Set ``smell_burden`` on each metrics dict using per-run count normalization.

    ``norm(smell_count)`` is ``count / max(1, max count in this batch)`` so values
    stay in ``[0, 1]`` within one analysis run. Formula::

        smell_burden = 0.5 * norm(smell_count) + 0.5 * smell_severity
    """
    if not metrics_dicts:
        return
    max_c = max(int(m["smell_count"]) for m in metrics_dicts)
    denom = max(1, max_c)
    for m in metrics_dicts:
        cnt = int(m["smell_count"])
        norm = cnt / denom
        sev = float(m.get("smell_severity", 0.0))
        m["smell_burden"] = 0.5 * norm + 0.5 * sev
