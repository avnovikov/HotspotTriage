from pathlib import Path

import pytest

from code_complexity_py.stats import (
    Statistic,
    aggregate_by_directory,
    build_stats,
    sort_and_limit,
)
from tests.fixtures.build_repo import build_repo


def _stat(path: str, **overrides) -> Statistic:
    base = dict(
        sloc=0, cyclomatic=0, halstead=0, maintainability=0, churn=0, score=0
    )
    base.update(overrides)
    return Statistic(path=path, **base)


def test_score_is_product_of_chosen_metrics(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    files = ["a.py", "b.py", "c/d.py"]
    churn = {"a.py": 4, "b.py": 1, "c/d.py": 2}
    stats = build_stats(repo, files, churn, score_metrics=["churn", "cyclomatic"])
    by = {s.path: s for s in stats}
    # b.py has 1 function with no branches → cyclomatic 1, churn 1, score 1.
    assert by["b.py"].cyclomatic == 1 and by["b.py"].churn == 1 and by["b.py"].score == 1
    # c/d.py final has if/elif/else → cyclomatic 3, churn 2, score 6.
    assert by["c/d.py"].cyclomatic == 3 and by["c/d.py"].churn == 2 and by["c/d.py"].score == 6


def test_score_with_three_metrics_multiplies_all(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    files = ["c/d.py"]
    churn = {"c/d.py": 2}
    stats = build_stats(
        repo, files, churn, score_metrics=["churn", "cyclomatic", "sloc"]
    )
    s = stats[0]
    assert s.score == s.churn * s.cyclomatic * s.sloc


def test_single_metric_score_equals_that_metric(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    files = ["a.py"]
    churn = {"a.py": 4}
    stats = build_stats(repo, files, churn, score_metrics=["churn"])
    assert stats[0].score == stats[0].churn == 4


def test_aggregate_by_directory_sums_all_metrics_and_recomputes_score():
    stats = [
        _stat("src/a.py", sloc=10, cyclomatic=2, halstead=20, maintainability=30, churn=2),
        _stat("src/lib/b.py", sloc=4, cyclomatic=1, halstead=8, maintainability=10, churn=5),
        _stat("docs/x.py", sloc=1, cyclomatic=1, halstead=1, maintainability=1, churn=1),
    ]
    out = {s.path: s for s in aggregate_by_directory(stats, ["churn", "cyclomatic"])}
    assert set(out) == {"src", "src/lib", "docs"}
    src = out["src"]
    assert src.sloc == 14 and src.cyclomatic == 3 and src.halstead == 28
    assert src.maintainability == 40 and src.churn == 7
    assert src.score == 7 * 3  # churn × cyclomatic


def test_sort_by_score_desc():
    stats = [_stat("a", score=1), _stat("b", score=25), _stat("c", score=9)]
    assert [s.path for s in sort_and_limit(stats, by="score")] == ["b", "c", "a"]


def test_sort_by_file_alpha():
    stats = [_stat("z"), _stat("a"), _stat("m")]
    assert [s.path for s in sort_and_limit(stats, by="file")] == ["a", "m", "z"]


def test_limit_applies_after_sort():
    stats = [_stat(str(i), score=i) for i in range(5)]
    assert [s.path for s in sort_and_limit(stats, by="score", limit=2)] == ["4", "3"]


def test_unknown_sort_raises():
    with pytest.raises(ValueError, match="unknown sort key"):
        sort_and_limit([], by="bogus")
