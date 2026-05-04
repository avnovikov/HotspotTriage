"""Render Statistic lists as table / json / csv. Always emits all metrics."""
from __future__ import annotations

import csv
import io
import json
from typing import Iterable

from tabulate import tabulate

from code_complexity_py.stats import Statistic

Format = str
FORMATS: tuple[Format, ...] = ("table", "json", "csv")
HEADERS: tuple[str, ...] = (
    "path",
    "sloc",
    "cyclomatic",
    "halstead",
    "maintainability",
    "churn",
    "score",
)


def _rows(stats: Iterable[Statistic]) -> list[tuple]:
    return [
        (s.path, s.sloc, s.cyclomatic, s.halstead, s.maintainability, s.churn, s.score)
        for s in stats
    ]


def render_table(stats: Iterable[Statistic]) -> str:
    return tabulate(_rows(stats), headers=HEADERS, tablefmt="github")


def render_json(stats: Iterable[Statistic]) -> str:
    return json.dumps([s.as_dict() for s in stats])


def render_csv(stats: Iterable[Statistic]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(HEADERS)
    w.writerows(_rows(stats))
    return buf.getvalue().rstrip("\n")


def render(stats: Iterable[Statistic], fmt: Format) -> str:
    if fmt == "table":
        return render_table(stats)
    if fmt == "json":
        return render_json(stats)
    if fmt == "csv":
        return render_csv(stats)
    raise ValueError(f"unknown format: {fmt!r} (valid: {FORMATS})")
