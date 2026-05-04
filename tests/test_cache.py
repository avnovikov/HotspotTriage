import json
from pathlib import Path

import pytest

from code_complexity_py.cache import Cache, cache_path_for


def test_cache_path_under_xdg_cache_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    p = cache_path_for(Path("/some/repo"))
    assert p.parent == tmp_path / "code-complexity-py"
    assert p.suffix == ".json"


def test_cache_path_is_stable_for_same_repo(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    a = cache_path_for(Path("/some/repo"))
    b = cache_path_for(Path("/some/repo"))
    assert a == b


def test_get_returns_none_for_missing_key(tmp_path: Path):
    c = Cache(tmp_path / "c.json")
    assert c.get("nope") is None


def test_put_then_get(tmp_path: Path):
    c = Cache(tmp_path / "c.json")
    c.put("k", 42)
    assert c.get("k") == 42


def test_save_writes_file_and_persists(tmp_path: Path):
    p = tmp_path / "c.json"
    c = Cache(p)
    c.put("k", 7)
    c.save()
    assert json.loads(p.read_text()) == {"k": 7}
    # Reopen and read back.
    c2 = Cache(p)
    assert c2.get("k") == 7


def test_save_skips_when_clean(tmp_path: Path):
    p = tmp_path / "c.json"
    c = Cache(p)
    c.save()
    # Nothing written because nothing was put.
    assert not p.exists()


def test_corrupt_file_recovers_to_empty(tmp_path: Path):
    p = tmp_path / "c.json"
    p.write_text("not json {{{")
    c = Cache(p)
    assert c.data == {}
    assert c.get("k") is None


def test_make_key_mixes_all_inputs():
    a = Cache.make_key("blob", 1, 10, None, None)
    b = Cache.make_key("blob", 1, 11, None, None)
    c = Cache.make_key("other", 1, 10, None, None)
    d = Cache.make_key("blob", 1, 10, "2024-01-01", None)
    assert len({a, b, c, d}) == 4
