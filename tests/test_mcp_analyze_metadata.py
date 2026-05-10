"""Tests for :mod:`hotspottriage.mcp.analyze_metadata`."""

from pathlib import Path

from hotspottriage.mcp.analyze_metadata import build_analyze_metadata
from hotspottriage.stats import Statistic


def _stat(path: str) -> Statistic:
    return Statistic(
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


def test_build_analyze_metadata_truncation_and_counts() -> None:
    cfg: dict[str, object] = {
        "filter": ["src/**/*.py"],
        "no_default_filter": True,
    }
    full = [_stat("a.py::f"), _stat("__x__::agg"), _stat("b.py::g")]
    limited = [_stat("a.py::f")]
    meta = build_analyze_metadata(
        cfg,
        "/repo",
        full,
        limited,
        analyzed_at="2026-05-10T12:00:00Z",
    )
    assert meta["row_count"] == 2
    assert meta["truncated"] is True
    assert meta["analyzed_at"] == "2026-05-10T12:00:00Z"
    assert meta["target"] == "/repo"
    assert meta["git_head"] is None
    assert meta["git_branch"] is None
    assert meta["filter_applied"] == ["src/**/*.py"]
    assert meta["config_fingerprint"].startswith("sha256:")


def test_build_analyze_metadata_snapshot_git_labels(monkeypatch, tmp_path: Path) -> None:
    cfg: dict[str, object] = {
        "filter": [],
        "default_filter": "**/*.py",
        "no_default_filter": False,
    }
    repo = tmp_path / "r"
    repo.mkdir()
    monkeypatch.setattr(
        "hotspottriage.mcp.analyze_metadata.git_short_object_name",
        lambda _r, _s: "abc1234",
    )
    meta = build_analyze_metadata(
        cfg,
        str(repo),
        [_stat("x.py::f")],
        [_stat("x.py::f")],
        git_repo=repo,
        snapshot_commit_full="deadbeef",
        analyzed_at="2026-01-01T00:00:00Z",
    )
    assert meta["git_head"] == "abc1234"
    assert meta["git_branch"] == "snapshot"
