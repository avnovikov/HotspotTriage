"""Tests for :mod:`hotspottriage.mcp.block_row_utils`."""

from hotspottriage.mcp.block_row_utils import (
    block_metric_row_repo_file,
    is_block_row_for_delta,
    metric_triplet,
    non_synthetic_block_rows,
    normal_block_stat_count,
    rows_equal_raw,
)
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


def test_is_block_row_for_delta() -> None:
    assert is_block_row_for_delta(_stat("f.py::fn")) is True
    assert is_block_row_for_delta(_stat("f.py::fn", score_band="aggregate")) is False
    assert is_block_row_for_delta(_stat("__agg__::x")) is False
    assert is_block_row_for_delta(_stat("f.py")) is False


def test_metric_triplet() -> None:
    assert metric_triplet(1, 3) == {"before": 1, "after": 3, "delta": 2}
    assert metric_triplet(None, 3)["before"] is None


def test_rows_equal_raw_float_tolerance() -> None:
    a = _stat("p::x", churn_per_sloc=0.1, decayed_churn=1.0, decayed_churn_per_sloc=0.2)
    b = _stat(
        "p::x",
        churn_per_sloc=0.1 + 1e-9,
        decayed_churn=1.0,
        decayed_churn_per_sloc=0.2,
    )
    assert rows_equal_raw(a, b) is True


def test_non_synthetic_and_normal_count() -> None:
    rows = [_stat("__x__::agg"), _stat("a.py::f")]
    assert len(non_synthetic_block_rows(rows)) == 1
    assert normal_block_stat_count(rows) == 1


def test_block_metric_row_repo_file() -> None:
    assert block_metric_row_repo_file(r"a\b.py::foo") == "a/b.py"
