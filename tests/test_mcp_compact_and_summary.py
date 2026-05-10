"""Tests for :mod:`hotspottriage.mcp.compact_score_rows` and ``analyze_summary``."""

from hotspottriage.mcp.analyze_summary import build_mcp_analyze_summary
from hotspottriage.mcp.compact_score_rows import compact_score_rows
from hotspottriage.stats import Statistic


def _stat(path: str, **kwargs: object) -> Statistic:
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
        score=1.0,
        score_band="low",
    )
    base.update(kwargs)
    return Statistic(**base)


def test_build_mcp_analyze_summary_empty() -> None:
    assert build_mcp_analyze_summary([])["block_count"] == 0


def test_build_mcp_analyze_summary_excludes_synthetic() -> None:
    rows = [_stat("__x__::agg", cyclomatic=99), _stat("a.py::f", cyclomatic=5, score=0.5)]
    s = build_mcp_analyze_summary(rows)
    assert s["block_count"] == 1
    assert s["sum_cyclomatic"] == 5
    assert s["max_cyclomatic"]["path"] == "a.py::f"


def test_compact_score_rows_block_granularity() -> None:
    cfg: dict[str, object] = {"proposed_models": {}}
    rows = [_stat("pkg/mod.py::foo", score=0.42, score_band="medium")]
    out = compact_score_rows(rows, granularity="block", merged_config=cfg)
    assert len(out) == 1
    assert out[0]["file"] == "pkg/mod.py"
    assert out[0]["function"] == "foo"
    assert out[0]["score"] == 0.42
    assert out[0]["risk_band"] == "medium"
