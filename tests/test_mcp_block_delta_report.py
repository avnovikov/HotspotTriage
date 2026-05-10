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


def test_build_block_delta_report_modified_and_summary_deltas() -> None:
    path = "src/m.py::fn"
    base = [_row(path, cyclomatic=3, sloc=10, halstead=50, churn=5, smell_count=0)]
    head = [_row(path, cyclomatic=7, sloc=12, halstead=55, churn=8, smell_count=1)]
    out = build_block_delta_report(head, base)
    assert out["summary"]["blocks_modified"] == 1
    assert out["summary"]["blocks_unchanged"] == 0
    assert out["summary"]["total_cyclomatic_delta"] == 4
    assert out["summary"]["total_sloc_delta"] == 2
    assert out["summary"]["total_halstead_delta"] == 5
    assert out["summary"]["total_churn_delta"] == 3
    assert out["summary"]["total_smell_count_delta"] == 1
    entry = out["by_block"][0]
    assert entry["path"] == path
    assert entry["status"] == "modified"
    assert entry["cyclomatic"] == {"before": 3, "after": 7, "delta": 4}
    assert entry["score"]["before"] is not None and entry["score"]["after"] is not None


def test_build_block_delta_report_removed_and_score_triplets() -> None:
    path = "legacy.py::gone"
    base = [_row(path, cyclomatic=2, score=0.3)]
    head: list[Statistic] = []
    out = build_block_delta_report(head, base)
    assert out["summary"]["blocks_removed"] == 1
    assert out["summary"]["total_cyclomatic_delta"] == -2
    entry = out["by_block"][0]
    assert entry["status"] == "removed"
    assert entry["cyclomatic"] == {"before": 2, "after": None, "delta": None}
    assert entry["score"] == {"before": 0.3, "after": None, "delta": None}


def test_build_block_delta_report_unchanged_excluded_from_by_block() -> None:
    path = "k.py::same"
    row = _row(path, cyclomatic=4)
    out = build_block_delta_report([row], [row])
    assert out["summary"]["blocks_unchanged"] == 1
    assert out["summary"]["blocks_added"] == 0
    assert out["by_block"] == []


def test_build_block_delta_report_ignores_file_only_and_aggregate_rows() -> None:
    """Rows without ``::``, ``score_band=aggregate``, and synthetic paths are not compared."""
    head = [
        _row("not_a_block_row.py", cyclomatic=99),
        _row("real.py::f", cyclomatic=1),
        _row("__synth__::agg", cyclomatic=1),
        _row("z.py::agg_row", cyclomatic=1, score_band="aggregate"),
    ]
    base = [_row("real.py::f", cyclomatic=1)]
    out = build_block_delta_report(head, base)
    assert out["summary"]["blocks_unchanged"] == 1
    assert out["summary"]["blocks_added"] == 0
    assert out["by_block"] == []
