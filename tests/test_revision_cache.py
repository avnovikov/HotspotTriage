"""Tests for :mod:`hotspottriage.revision_cache`."""
from __future__ import annotations

import pickle
import subprocess
from pathlib import Path

import pytest

from hotspottriage import config as _config
from hotspottriage import stats
from hotspottriage.revision_cache import (
    REVISION_CACHE_VERSION,
    RevisionCacheManager,
    SnapshotNotFoundError,
    clear_revision_cache_file,
    head_commit_sha,
    resolve_commit_sha,
    revisions_cache_path,
    statistic_from_dict,
)


@pytest.fixture
def tiny_git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "revcache_repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "t@e.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "t"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "m.py").write_text("def f():\n    return 1\n")
    subprocess.run(["git", "add", "m.py"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return repo


def test_head_and_resolve_commit_sha(tiny_git_repo: Path) -> None:
    h = head_commit_sha(tiny_git_repo)
    assert len(h) == 40
    assert resolve_commit_sha(tiny_git_repo, "HEAD") == h


def test_record_snapshot_roundtrip(tiny_git_repo: Path) -> None:
    cfg = _config.load_analyze_config_for_local_repo(tiny_git_repo)
    rows = stats.build_block_stats(
        tiny_git_repo,
        ["m.py"],
        cfg["score_metrics"],
        runtime=stats.BlockStatsRuntime(merged_config=cfg),
        similarity=stats.BlockSimilarityConfig(enabled=False),
    )
    mgr = RevisionCacheManager(tiny_git_repo)
    sha = mgr.record_snapshot(rows)
    assert sha == head_commit_sha(tiny_git_repo)
    back = mgr.get_snapshot_statistics(sha)
    assert {str(r.path) for r in back} == {str(r.path) for r in rows}


@pytest.fixture
def two_commit_repo(tmp_path: Path) -> Path:
    """Two commits touching ``a.py`` (same layout as ``rev_pair_repo`` in MCP tests)."""
    repo = tmp_path / "two_commit"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "t@e.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "t"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "a.py").write_text("def only():\n    return 1\n")
    subprocess.run(["git", "add", "a.py"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "c1"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "a.py").write_text(
        "def only():\n    return 1\n\ndef second():\n    return 2\n"
    )
    subprocess.run(["git", "add", "a.py"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "c2"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return repo


def test_get_snapshot_missing_raises(two_commit_repo: Path) -> None:
    root = subprocess.check_output(
        ["git", "-C", str(two_commit_repo), "rev-list", "--max-parents=0", "HEAD"],
        text=True,
    ).strip()
    mgr = RevisionCacheManager(two_commit_repo)
    with pytest.raises(SnapshotNotFoundError):
        mgr.get_snapshot_statistics(root)


def test_statistic_from_dict_roundtrip(tiny_git_repo: Path) -> None:
    cfg = _config.load_analyze_config_for_local_repo(tiny_git_repo)
    rows = stats.build_block_stats(
        tiny_git_repo,
        ["m.py"],
        cfg["score_metrics"],
        runtime=stats.BlockStatsRuntime(merged_config=cfg),
        similarity=stats.BlockSimilarityConfig(enabled=False),
    )
    assert rows
    s0 = rows[0]
    s1 = statistic_from_dict(s0.as_dict())
    assert s1 == s0


def test_version_mismatch_starts_fresh(tiny_git_repo: Path) -> None:
    p = revisions_cache_path(tiny_git_repo)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "wb") as f:
        pickle.dump({"__cache_version": 0, "obj": {}}, f)
    mgr = RevisionCacheManager(tiny_git_repo)
    assert mgr.list_snapshots() == []


def test_clear_revision_cache_file(tiny_git_repo: Path) -> None:
    cfg = _config.load_analyze_config_for_local_repo(tiny_git_repo)
    rows = stats.build_block_stats(
        tiny_git_repo,
        ["m.py"],
        cfg["score_metrics"],
        runtime=stats.BlockStatsRuntime(merged_config=cfg),
        similarity=stats.BlockSimilarityConfig(enabled=False),
    )
    RevisionCacheManager(tiny_git_repo).record_snapshot(rows)
    assert revisions_cache_path(tiny_git_repo).exists()
    assert clear_revision_cache_file(tiny_git_repo) is True
    assert not revisions_cache_path(tiny_git_repo).exists()


def test_flush_preserves_version_envelope(tiny_git_repo: Path) -> None:
    cfg = _config.load_analyze_config_for_local_repo(tiny_git_repo)
    rows = stats.build_block_stats(
        tiny_git_repo,
        ["m.py"],
        cfg["score_metrics"],
        runtime=stats.BlockStatsRuntime(merged_config=cfg),
        similarity=stats.BlockSimilarityConfig(enabled=False),
    )
    RevisionCacheManager(tiny_git_repo).record_snapshot(rows)
    with open(revisions_cache_path(tiny_git_repo), "rb") as f:
        raw = pickle.load(f)
    assert raw["__cache_version"] == REVISION_CACHE_VERSION
