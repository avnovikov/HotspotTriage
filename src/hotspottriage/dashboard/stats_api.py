"""JSON helpers for dashboard ``/api/stats/*`` endpoints (heatmap matrix, histograms, SSE)."""
from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator, Callable

# Numeric Statistic fields eligible for /api/stats/distribution histograms.
DISTRIBUTION_METRICS: frozenset[str] = frozenset(
    {
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
        "score",
    }
)

# Upper cap for ``/api/stats/heatmap`` limit (query param).
HEATMAP_MAX_LIMIT = 500

HEATMAP_SCORE_COLUMNS: tuple[str, ...] = (
    "score",
    "complexity_burden",
    "churn_burden",
    "maintainability_burden",
    "smell_burden",
    "similarity_burden",
)


def split_block_path(raw_path: str) -> tuple[str, str]:
    path = str(raw_path).strip()
    if not path:
        return "", ""
    if "::" not in path:
        return path, ""
    file_path, symbol = path.split("::", 1)
    return file_path, symbol


def as_float_or_zero(raw: Any) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def build_heatmap_rows(rows: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    """Return matrix rows sorted by file score, then method score."""
    table_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        path = row.get("path")
        if not path:
            continue
        file_path, method_name = split_block_path(str(path))
        subs = row.get("score_subscores")
        subs_map = subs if isinstance(subs, dict) else {}
        item: dict[str, Any] = {
            "path": str(path),
            "file": file_path,
            "method": method_name,
        }
        for col in HEATMAP_SCORE_COLUMNS:
            value = row.get(col)
            if value is None:
                value = subs_map.get(col)
            item[col] = as_float_or_zero(value)
        band = row.get("score_band")
        if band is not None and str(band).strip():
            item["score_band"] = str(band)
        table_rows.append(item)

    file_max_score: dict[str, float] = {}
    for row in table_rows:
        file_name = str(row["file"])
        score = as_float_or_zero(row.get("score"))
        prev = file_max_score.get(file_name)
        if prev is None or score > prev:
            file_max_score[file_name] = score

    table_rows.sort(
        key=lambda r: (
            -file_max_score.get(str(r["file"]), 0.0),
            str(r["file"]),
            -as_float_or_zero(r.get("score")),
            str(r["method"]),
        )
    )
    return table_rows[:limit]


def heatmap_column_maxima(
    table_rows: list[dict[str, Any]], *, columns: tuple[str, ...]
) -> dict[str, float]:
    """Per-column maxima for heatmap cell tinting.

    Excludes meta rows whose ``path`` starts with ``__`` (e.g. similarity aggregate),
    which often have an outsized ``score`` and would flatten tinting for real blocks.
    """
    eligible = [r for r in table_rows if not str(r.get("path", "")).startswith("__")]
    if not eligible:
        eligible = table_rows
    out: dict[str, float] = {}
    for col in columns:
        vals = [as_float_or_zero(r.get(col)) for r in eligible]
        m = float(max(vals)) if vals else 0.0
        out[col] = m if m > 0 else 1e-9
    return out


def histogram_buckets(
    values: list[float], *, bins: int = 20
) -> tuple[list[list[float]], list[int]]:
    """Return ``buckets`` as ``[low, high]`` pairs and ``counts`` (same length)."""
    if not values:
        return [], []
    if bins < 1:
        raise ValueError("bins must be positive")
    vmin = float(min(values))
    vmax = float(max(values))
    if vmin == vmax:
        return [[vmin, vmax]], [len(values)]
    width = (vmax - vmin) / bins
    counts = [0] * bins
    buckets: list[list[float]] = []
    for i in range(bins):
        lo = vmin + i * width
        hi = vmin + (i + 1) * width
        if i == bins - 1:
            hi = vmax
        buckets.append([lo, hi])
    for v in values:
        fv = float(v)
        if fv >= vmax:
            idx = bins - 1
        elif fv <= vmin:
            idx = 0
        else:
            idx = int((fv - vmin) / width)
            if idx >= bins:
                idx = bins - 1
        counts[idx] += 1
    return buckets, counts


async def sse_json_every(
    interval_s: float,
    build_payload: Callable[[], Any],
) -> AsyncGenerator[str, None]:
    """SSE stream: emit JSON snapshots on a fixed interval."""
    while True:
        yield "data: " + json.dumps(build_payload()) + "\n\n"
        await asyncio.sleep(interval_s)
