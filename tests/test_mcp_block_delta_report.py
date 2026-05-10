"""Tests for :mod:`hotspottriage.mcp.block_delta_report`."""

from hotspottriage.mcp.block_delta_report import build_block_delta_report
from hotspottriage.stats import Statistic


def _row(path: str, **kw: object) -> Statistic:
    base: dict[str, object] = dict(
        path=path,
        sloc=10,
        normalized_sloc=0.0,
        cyclomatic=3,
        halstead=50,
        maintainability=50,
        churn=5,
        churn_per_sloc=0.5,
        decayed_churn=5.0,
        decayed_churn_per_sloc=0.5,
        smell_count=0,
        smell_severity=0.0,
        smell_burden=0.0,
        smells={},
        similarity_score=0.0,
        similarity_band="n/a",
        match_count=0,
        score=0.5,
        score_band="low",
    )
    base.update(kw)
    return Statistic(**base)


def test_build_block_delta_report_detects_added() -> None:
    head = [_row("a.py::f", cyclomatic=5)]
    base: list[Statistic] = []
    out = build_block_delta_report(head, base)
    assert out["summary"]["blocks_added"] == 1
    assert out["by_block"][0]["status"] == "added"
