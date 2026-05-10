"""Render Statistic lists as table / json / csv. Always emits all metrics.

Floats (`churn_per_sloc`, `score`) are formatted to 4 decimal places in table
and CSV outputs for readability; JSON emits raw floats.

When ``merged_config`` is passed to :func:`render`, ``metric_normalization`` is
applied and ``norm_<metric>`` columns are appended for each configured metric.
"""
from __future__ import annotations

import csv
import io
import json
from typing import Any, Iterable

from tabulate import tabulate

from hotspottriage import normalize as _normalize
from hotspottriage import explain as _explain
from hotspottriage.statistic_row import Statistic

Format = str
FORMATS: tuple[Format, ...] = ("table", "json", "csv")

# Raw statistic columns (no norm_*); stable public order for CSV/CLI.
HEADERS: tuple[str, ...] = (
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
    "smells",
    "similarity_score",
    "similarity_band",
    "match_count",
    "score",
    "score_band",
    "score_subscores",
    "score_driver",
    "score_explanation",
    "score_narrative",
)


def _metric_normalization(merged_config: dict[str, Any] | None) -> dict[str, Any]:
    if not merged_config:
        return {}
    mn = merged_config.get("metric_normalization")
    return mn if isinstance(mn, dict) else {}


def normalization_suffix_headers(merged_config: dict[str, Any] | None) -> tuple[str, ...]:
    """Return ``norm_<metric>`` header names in config key order."""
    mn = _metric_normalization(merged_config)
    return tuple(f"norm_{k}" for k in mn.keys())


def display_headers(merged_config: dict[str, Any] | None) -> tuple[str, ...]:
    """All column names written for the given config (raw + optional norm_*)."""
    return HEADERS + normalization_suffix_headers(merged_config)


def proposed_model_for_band(
    score_band: str, merged_config: dict[str, Any] | None
) -> str:
    """Config ``proposed_models`` entry for ``score_band`` (MCP / CLI JSON parity)."""
    if not merged_config:
        return ""
    proposed = merged_config.get("proposed_models")
    if not isinstance(proposed, dict):
        return ""
    key = str(score_band).strip().lower()
    model = proposed.get(key)
    return model if isinstance(model, str) else ""


def score_narrative_text(
    s: Statistic, merged_config: dict[str, Any] | None
) -> str:
    """Multi-line score narrative; uses ``proposed_models`` like MCP full rows."""
    if not s.score_subscores:
        return ""
    pm = proposed_model_for_band(str(s.score_band), merged_config)
    rec: str | None = pm if pm else None
    return _explain.explain_score(
        s, recommended_action=rec, final_weights=s.score_final_weights
    )


def statistic_to_output_dict(
    s: Statistic, merged_config: dict[str, Any] | None
) -> dict[str, Any]:
    """``Statistic`` as dict, optionally augmented with ``norm_*`` fields."""
    row: dict[str, Any] = s.as_dict()
    row["proposed_model"] = proposed_model_for_band(str(s.score_band), merged_config)
    row["rationale"] = (
        _explain.compact_agent_rationale(s, final_weights=s.score_final_weights)
        if s.score_subscores
        else ""
    )
    row["score_narrative"] = score_narrative_text(s, merged_config)
    mn = _metric_normalization(merged_config)
    if not mn:
        return row
    return _normalize.normalize_record(row, mn)


def _row_tuple(s: Statistic, merged_config: dict[str, Any] | None) -> tuple[Any, ...]:
    base = (
        s.path,
        s.sloc,
        s.normalized_sloc,
        s.cyclomatic,
        s.halstead,
        s.maintainability,
        s.churn,
        s.churn_per_sloc,
        s.decayed_churn,
        s.decayed_churn_per_sloc,
        s.smell_count,
        s.smell_severity,
        s.smell_burden,
        json.dumps(s.smells),
        s.similarity_score,
        s.similarity_band,
        s.match_count,
        s.score,
        s.score_band,
        json.dumps(s.score_subscores, sort_keys=True),
        s.score_driver,
        json.dumps(s.score_explanation),
        score_narrative_text(s, merged_config),
    )
    if not _metric_normalization(merged_config):
        return base
    aug = statistic_to_output_dict(s, merged_config)
    suf = normalization_suffix_headers(merged_config)
    return base + tuple(aug[k] for k in suf)


def _fmt_float(x: float) -> str:
    return f"{x:.4f}"


def render_table(stats: Iterable[Statistic], merged_config: dict[str, Any] | None = None) -> str:
    headers = display_headers(merged_config)
    return tabulate(
        [_row_tuple(s, merged_config) for s in stats],
        headers=headers,
        tablefmt="github",
        floatfmt=".4f",
    )


def render_json(stats: Iterable[Statistic], merged_config: dict[str, Any] | None = None) -> str:
    rows = [statistic_to_output_dict(s, merged_config) for s in stats]
    return json.dumps(rows)


def render_csv(stats: Iterable[Statistic], merged_config: dict[str, Any] | None = None) -> str:
    headers = display_headers(merged_config)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    mn = _metric_normalization(merged_config)
    for s in stats:
        base = (
            s.path,
            s.sloc,
            _fmt_float(s.normalized_sloc),
            s.cyclomatic,
            s.halstead,
            s.maintainability,
            s.churn,
            _fmt_float(s.churn_per_sloc),
            _fmt_float(s.decayed_churn),
            _fmt_float(s.decayed_churn_per_sloc),
            s.smell_count,
            _fmt_float(s.smell_severity),
            _fmt_float(s.smell_burden),
            json.dumps(s.smells),
            _fmt_float(s.similarity_score),
            s.similarity_band,
            s.match_count,
            _fmt_float(s.score),
            s.score_band,
            json.dumps(s.score_subscores, sort_keys=True),
            s.score_driver,
            json.dumps(s.score_explanation),
            score_narrative_text(s, merged_config),
        )
        if not mn:
            w.writerow(base)
            continue
        aug = statistic_to_output_dict(s, merged_config)
        suf = normalization_suffix_headers(merged_config)
        extra = tuple(_fmt_float(float(aug[k])) for k in suf)
        w.writerow(base + extra)
    return buf.getvalue().rstrip("\n")


def render(
    stats: Iterable[Statistic],
    fmt: Format,
    merged_config: dict[str, Any] | None = None,
) -> str:
    if fmt == "table":
        return render_table(stats, merged_config=merged_config)
    if fmt == "json":
        return render_json(stats, merged_config=merged_config)
    if fmt == "csv":
        return render_csv(stats, merged_config=merged_config)
    raise ValueError(f"unknown format: {fmt!r} (valid: {list(FORMATS)})")
