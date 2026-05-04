from pathlib import Path

import pytest

from code_complexity_py.stats import (
    Statistic,
    aggregate_by_directory,
    build_stats,
    sort_and_limit,
)
from tests.fixtures.build_repo import build_repo


def test_score_is_complexity_times_churn():
    s = Statistic(path="x.py", complexity=7, churn=3)
    assert s.score == 21
    assert s.as_dict() == {"path": "x.py", "complexity": 7, "churn": 3, "score": 21}


def test_build_stats_produces_one_per_file(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    files = ["a.py", "b.py", "c/d.py"]
    churn = {"a.py": 4, "b.py": 1, "c/d.py": 2}
    stats = build_stats(repo, files, churn, strategy="cyclomatic")
    by_path = {s.path: s for s in stats}
    assert set(by_path) == set(files)
    # b.py has a function with no branches → cyclomatic = 1
    assert by_path["b.py"].complexity == 1
    assert by_path["b.py"].churn == 1
    # c/d.py final version has if/elif/else → cyclomatic = 3
    assert by_path["c/d.py"].complexity == 3
    assert by_path["c/d.py"].score == 3 * 2


def test_aggregate_by_directory_sums_descendants():
    stats = [
        Statistic("src/a.py", complexity=10, churn=2),
        Statistic("src/lib/b.py", complexity=4, churn=5),
        Statistic("docs/x.py", complexity=1, churn=1),
    ]
    by = {s.path: s for s in aggregate_by_directory(stats)}
    assert set(by) == {"src", "src/lib", "docs"}
    assert by["src"].complexity == 14 and by["src"].churn == 7
    assert by["src/lib"].complexity == 4 and by["src/lib"].churn == 5
    assert by["docs"].complexity == 1 and by["docs"].churn == 1


def test_sort_by_score_desc():
    stats = [
        Statistic("a", 1, 1),  # score 1
        Statistic("b", 5, 5),  # score 25
        Statistic("c", 3, 3),  # score 9
    ]
    out = sort_and_limit(stats, by="score")
    assert [s.path for s in out] == ["b", "c", "a"]


def test_sort_by_file_alpha():
    stats = [Statistic("z", 1, 1), Statistic("a", 1, 1), Statistic("m", 1, 1)]
    out = sort_and_limit(stats, by="file")
    assert [s.path for s in out] == ["a", "m", "z"]


def test_limit_applies_after_sort():
    stats = [Statistic(str(i), i, 1) for i in range(5)]
    out = sort_and_limit(stats, by="complexity", limit=2)
    assert [s.path for s in out] == ["4", "3"]


def test_unknown_sort_raises():
    with pytest.raises(ValueError, match="unknown sort key"):
        sort_and_limit([], by="bogus")
