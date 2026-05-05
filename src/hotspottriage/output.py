"""Render Statistic lists as table / json / csv. Always emits all metrics.

Floats (`churn_per_sloc`, `score`) are formatted to 4 decimal places in table
and CSV outputs for readability; JSON emits raw floats.
"""
from __future__ import annotations

import csv
import io
import json
from typing import Iterable

from tabulate import tabulate

from hotspottriage.stats import Statistic

Format = str
FORMATS: tuple[Format, ...] = ("table", "json", "csv")
HEADERS: tuple[str, ...] = (
    "path",
    "sloc",
    "cyclomatic",
    "halstead",
    "maintainability",
    "churn",
    "churn_per_sloc",
    "decayed_churn",
    "decayed_churn_per_sloc",
    "score",
)


def _row(s: Statistic) -> tuple:
    return (
        s.path,
        s.sloc,
        s.cyclomatic,
        s.halstead,
        s.maintainability,
        s.churn,
        s.churn_per_sloc,
        s.decayed_churn,
        s.decayed_churn_per_sloc,
        s.score,
    )


def _fmt_float(x: float) -> str:
    return f"{x:.4f}"


def render_table(stats: Iterable[Statistic]) -> str:
    return tabulate(
        [_row(s) for s in stats],
        headers=HEADERS,
        tablefmt="github",
        floatfmt=".4f",
    )


def render_json(stats: Iterable[Statistic]) -> str:
    return json.dumps([s.as_dict() for s in stats])


def render_csv(stats: Iterable[Statistic]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(HEADERS)
    for s in stats:
        w.writerow(
            (
                s.path,
                s.sloc,
                s.cyclomatic,
                s.halstead,
                s.maintainability,
                s.churn,
                _fmt_float(s.churn_per_sloc),
                _fmt_float(s.decayed_churn),
                _fmt_float(s.decayed_churn_per_sloc),
                _fmt_float(s.score),
            )
        )
    return buf.getvalue().rstrip("\n")


def render(stats: Iterable[Statistic], fmt: Format) -> str:
    if fmt == "table":
        return render_table(stats)
    if fmt == "json":
        return render_json(stats)
    if fmt == "csv":
        return render_csv(stats)
    raise ValueError(f"unknown format: {fmt!r} (valid: {FORMATS})")
