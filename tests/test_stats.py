from pathlib import Path
from statistics import mean

import pytest

from hotspottriage.config import DEFAULTS
from hotspottriage.stats import (
    Statistic,
    aggregate_by_directory,
    build_block_stats,
    build_stats,
    sort_and_limit,
)
from tests.fixtures.build_block_repo import build_block_repo
from tests.fixtures.build_repo import build_repo
from tests.fixtures.build_similarity_repo import build_similarity_repo


def _stat(path: str, **overrides) -> Statistic:
    base = dict(
        sloc=0, normalized_sloc=0.0, cyclomatic=0, halstead=0, maintainability=0,
        churn=0, churn_per_sloc=0.0, decayed_churn=0.0, decayed_churn_per_sloc=0.0,
        smell_count=0, smell_severity=0.0, smell_burden=0.0, smells={},
        similarity_score=0.0, similarity_band="n/a", match_count=0,
        score=0.0,
    )
    base.update(overrides)
    return Statistic(path=path, **base)


def test_churn_per_sloc_is_ratio(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    files = ["a.py", "b.py", "c/d.py"]
    # Pretend churn was 30 lines for a.py with sloc 4 -> ratio 7.5
    fake_churn = {"a.py": 30, "b.py": 0, "c/d.py": 0}
    stats = build_stats(repo, files, fake_churn, score_metrics=["churn_per_sloc"])
    by = {s.path: s for s in stats}
    assert by["a.py"].sloc > 0
    assert by["a.py"].churn_per_sloc == pytest.approx(30 / by["a.py"].sloc)


def test_churn_per_sloc_zero_when_sloc_zero():
    # Synthetic: a Statistic representing an unparseable file gets sloc=0.
    s = _stat("x.py", churn=10, sloc=0)
    assert s.churn_per_sloc == 0.0


def test_default_score_is_churn_per_sloc_times_cyclomatic(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    files = ["a.py", "b.py", "c/d.py"]
    fake_churn = {"a.py": 20, "b.py": 4, "c/d.py": 12}
    stats = build_stats(
        repo, files, fake_churn, score_metrics=["churn_per_sloc", "cyclomatic"]
    )
    for s in stats:
        assert s.score == pytest.approx(s.churn_per_sloc * s.cyclomatic)


def test_score_with_raw_churn_is_int_product(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    files = ["c/d.py"]
    fake_churn = {"c/d.py": 5}
    stats = build_stats(repo, files, fake_churn, score_metrics=["churn", "cyclomatic"])
    s = stats[0]
    assert s.score == s.churn * s.cyclomatic


def test_aggregate_recomputes_ratio_from_summed_totals():
    stats = [
        _stat("src/a.py", sloc=10, cyclomatic=2, halstead=20,
              maintainability=30, churn=20, churn_per_sloc=2.0),
        _stat("src/lib/b.py", sloc=4, cyclomatic=1, halstead=8,
              maintainability=10, churn=2, churn_per_sloc=0.5),
    ]
    out = {s.path: s for s in aggregate_by_directory(stats, ["churn_per_sloc", "cyclomatic"])}
    src = out["src"]
    # Aggregated churn=22, sloc=14 -> ratio = 22/14, NOT mean(2.0, 0.5).
    assert src.churn == 22 and src.sloc == 14
    assert src.churn_per_sloc == pytest.approx(22 / 14)
    assert src.cyclomatic == 3
    assert src.score == pytest.approx((22 / 14) * 3)


def test_sort_by_score_desc_with_floats():
    stats = [_stat("a", score=0.5), _stat("b", score=12.3), _stat("c", score=3.0)]
    assert [s.path for s in sort_and_limit(stats, by="score")] == ["b", "c", "a"]


def test_sort_by_file_alpha():
    stats = [_stat("z"), _stat("a"), _stat("m")]
    assert [s.path for s in sort_and_limit(stats, by="file")] == ["a", "m", "z"]


def test_limit_applies_after_sort():
    stats = [_stat(str(i), score=float(i)) for i in range(5)]
    assert [s.path for s in sort_and_limit(stats, by="score", limit=2)] == ["4", "3"]


def test_unknown_sort_raises():
    with pytest.raises(ValueError, match="unknown sort key"):
        sort_and_limit([], by="bogus")


def test_build_block_stats_similarity_deepcsim_pair(tmp_path: Path):
    repo = build_similarity_repo(tmp_path / "sim")
    rows = build_block_stats(
        repo,
        ["a.py", "b.py"],
        score_metrics=["cyclomatic"],
        similarity_enabled=True,
        similarity_aggregate_row=False,
        similarity_threshold=50.0,
    )
    assert len(rows) == 2
    by_path = {s.path: s for s in rows}
    assert by_path["a.py::twin"].match_count >= 1
    assert by_path["b.py::twin"].match_count >= 1
    assert by_path["a.py::twin"].similarity_score >= 50.0
    assert by_path["b.py::twin"].similarity_score >= 50.0


def test_block_stats_sets_normalized_sloc_zscore(tmp_path: Path):
    repo = build_block_repo(tmp_path / "r")
    stats = build_block_stats(
        repo,
        ["mod.py"],
        score_metrics=["cyclomatic"],
        similarity_enabled=False,
        similarity_aggregate_row=False,
        merged_config=DEFAULTS,
    )
    assert stats
    assert all(s.similarity_band == "off" for s in stats)
    normalized = [s.normalized_sloc for s in stats]
    # Z-score normalization is centered around zero.
    assert mean(normalized) == pytest.approx(0.0, abs=1e-9)
    # With varied block sizes in fixture, at least one row should be non-zero.
    assert any(abs(v) > 0 for v in normalized)
    for s in stats:
        assert 0.0 <= s.score <= 1.0
        assert s.score_band in ("low", "medium", "high", "critical")
        assert "complexity_burden" in s.score_subscores


def test_decay_reduces_churn_over_time():
    from hotspottriage.stats import _decayed_value
    
    # Original value
    original = 100.0
    half_life = 2592000  # 30 days in seconds
    
    # At time 0 (just created), decay should be minimal
    age_0 = 0
    decayed_0 = _decayed_value(original, age_0, half_life)
    assert decayed_0 == pytest.approx(100.0)
    
    # At half-life, value should be 50% of original
    age_half_life = half_life
    decayed_half = _decayed_value(original, age_half_life, half_life)
    assert decayed_half == pytest.approx(50.0)
    
    # At double half-life, value should be 25% of original
    age_double = half_life * 2
    decayed_double = _decayed_value(original, age_double, half_life)
    assert decayed_double == pytest.approx(25.0)
    
    # Decay should be monotonic: older = smaller value
    assert decayed_0 > decayed_half > decayed_double
