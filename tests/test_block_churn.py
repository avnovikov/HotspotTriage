from pathlib import Path

import pytest

from hotspottriage import block_churn
from hotspottriage.cache import Cache
from tests.fixtures.build_block_repo import build_block_repo


def test_file_blob_shas_lists_tracked_files(tmp_path: Path):
    repo = build_block_repo(tmp_path / "r")
    shas = block_churn.file_blob_shas(repo)
    assert "mod.py" in shas
    assert len(shas["mod.py"]) == 40  # SHA-1 hex


def test_compute_one_returns_positive_for_changed_block(tmp_path: Path):
    """Foo.bar was rewritten between v1 and v2 → its line range churns."""
    repo = build_block_repo(tmp_path / "r")
    # In v2, Foo.bar spans roughly lines 6-11. We give a generous range.
    n = block_churn.compute_one(repo, "mod.py", 6, 12, since=None, until=None)
    assert n > 0


def test_cache_round_trip(tmp_path: Path):
    """Two compute_many calls — second one should hit cache (no work)."""
    repo = build_block_repo(tmp_path / "r")
    shas = block_churn.file_blob_shas(repo)
    requests = [("mod.py", shas["mod.py"], 6, 12)]

    cache_a = Cache(repo)
    out_a = block_churn.compute_many(repo, requests, None, None, cache_a)
    cache_a.save()
    cache_pkl = repo / ".hotspottriage" / "cache" / "blocks.pkl"
    assert cache_pkl.exists()

    # Reload cache — second invocation must not call compute_one. We assert
    # that by patching compute_one to raise, then verifying we still get the
    # same answer from the cache.
    cache_b = Cache(repo)

    def fail(*a, **kw):
        raise AssertionError("cache miss — compute_one should not be called")

    import sys
    old_compute_one = block_churn.compute_one
    try:
        block_churn.compute_one = fail
        out_b = block_churn.compute_many(repo, requests, None, None, cache_b)
        assert out_a == out_b
    finally:
        block_churn.compute_one = old_compute_one


def test_cache_invalidates_when_file_changes(tmp_path: Path):
    """Mutating the file changes its blob SHA, so old cache entries no longer
    match and the new SHA forces a recompute."""
    repo = build_block_repo(tmp_path / "r")

    shas_before = block_churn.file_blob_shas(repo)
    cache = Cache(repo)
    block_churn.compute_many(repo, [("mod.py", shas_before["mod.py"], 6, 12)], None, None, cache)
    cache.save()

    # New commit changes the blob SHA.
    (repo / "mod.py").write_text((repo / "mod.py").read_text() + "\n# trailing\n")
    import subprocess
    subprocess.run(["git", "-C", str(repo), "commit", "-am", "tweak"], check=True, capture_output=True)
    shas_after = block_churn.file_blob_shas(repo)
    assert shas_after["mod.py"] != shas_before["mod.py"]

    cache2 = Cache(repo)
    assert cache2.get(Cache.make_key(shas_after["mod.py"], 6, 12, None, None)) is None
