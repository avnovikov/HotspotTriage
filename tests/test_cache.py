import pickle
from pathlib import Path

import pytest

from hotspottriage.cache import (
    cache_path_for,
    save_block_results,
    load_block_results,
    get_metadata,
    _CACHE_FILE,
)


def test_cache_path_in_project_hotspottriage(tmp_path: Path):
    p = cache_path_for(tmp_path / "myrepo")
    assert p == tmp_path / "myrepo" / ".hotspottriage" / "cache"


def test_cache_path_is_stable_for_same_repo(tmp_path: Path):
    a = cache_path_for(tmp_path / "myrepo")
    b = cache_path_for(tmp_path / "myrepo")
    assert a == b


def test_save_and_load_round_trip(tmp_path: Path):
    repo = tmp_path / "myrepo"
    rows = [
        {"path": "a.py::foo", "churn": 10, "_blob_sha": "abc", "_start": 1, "_end": 5},
        {"path": "a.py::bar", "churn": 20, "_blob_sha": "abc", "_start": 7, "_end": 12},
    ]
    save_block_results(repo, rows)
    loaded = load_block_results(repo)
    assert loaded == rows


def test_save_creates_cache_file(tmp_path: Path):
    repo = tmp_path / "myrepo"
    save_block_results(repo, [{"path": "x.py::f", "churn": 1}])
    pkl_path = cache_path_for(repo) / _CACHE_FILE
    assert pkl_path.exists()


def test_load_returns_none_when_no_cache(tmp_path: Path):
    assert load_block_results(tmp_path / "nope") is None


def test_load_returns_none_for_corrupt_file(tmp_path: Path):
    repo = tmp_path / "myrepo"
    cache_dir = cache_path_for(repo)
    cache_dir.mkdir(parents=True)
    (cache_dir / _CACHE_FILE).write_text("not pickle {{{")
    assert load_block_results(repo) is None


def test_save_writes_metadata(tmp_path: Path):
    repo = tmp_path / "myrepo"
    save_block_results(repo, [{"path": "x.py::f"}] * 3)
    meta = get_metadata(repo)
    assert meta is not None
    assert meta["entry_count"] == 3
    assert meta["version"] == 2
    assert "generated_at" in meta
