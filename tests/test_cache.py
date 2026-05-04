import pickle
from pathlib import Path

import pytest

from hotspottriage.cache import Cache, cache_path_for


def test_cache_path_in_project_hotspottriage(tmp_path: Path):
    p = cache_path_for(tmp_path / "myrepo")
    assert p == tmp_path / "myrepo" / ".hotspottriage" / "cache"


def test_cache_path_is_stable_for_same_repo(tmp_path: Path):
    a = cache_path_for(tmp_path / "myrepo")
    b = cache_path_for(tmp_path / "myrepo")
    assert a == b


def test_get_returns_none_for_missing_key(tmp_path: Path):
    c = Cache(tmp_path / "myrepo")
    assert c.get("nope") is None


def test_put_then_get(tmp_path: Path):
    c = Cache(tmp_path / "myrepo")
    c.put("k", 42)
    assert c.get("k") == 42


def test_save_writes_file_and_persists(tmp_path: Path):
    repo = tmp_path / "myrepo"
    c = Cache(repo)
    c.put("k", 7)
    c.save()
    # Cache should write to .hotspottriage/cache/blocks.pkl
    pkl_path = repo / ".hotspottriage" / "cache" / "blocks.pkl"
    assert pkl_path.exists()
    with open(pkl_path, "rb") as f:
        assert pickle.load(f) == {"k": 7}
    # Reopen and read back.
    c2 = Cache(repo)
    assert c2.get("k") == 7


def test_save_skips_when_clean(tmp_path: Path):
    repo = tmp_path / "myrepo"
    c = Cache(repo)
    c.save()
    # Nothing written because nothing was put.
    pkl_path = repo / ".hotspottriage" / "cache" / "blocks.pkl"
    assert not pkl_path.exists()


def test_corrupt_file_recovers_to_empty(tmp_path: Path):
    repo = tmp_path / "myrepo"
    cache_dir = repo / ".hotspottriage" / "cache"
    cache_dir.mkdir(parents=True)
    pkl_file = cache_dir / "blocks.pkl"
    pkl_file.write_text("not pickle {{{")
    c = Cache(repo)
    assert c.data == {}
    assert c.get("k") is None


def test_make_key_mixes_all_inputs():
    a = Cache.make_key("blob", 1, 10, None, None)
    b = Cache.make_key("blob", 1, 11, None, None)
    c = Cache.make_key("other", 1, 10, None, None)
    d = Cache.make_key("blob", 1, 10, "2024-01-01", None)
    assert len({a, b, c, d}) == 4
