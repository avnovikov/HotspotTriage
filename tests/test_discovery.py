from pathlib import Path

import pytest

from code_complexity_py import discovery
from tests.fixtures.build_repo import build_repo


def test_is_git_url_detects_remote():
    assert discovery.is_git_url("https://github.com/x/y.git")
    assert discovery.is_git_url("git@github.com:x/y.git")
    assert discovery.is_git_url("ssh://git@host/x.git")
    assert not discovery.is_git_url("/home/me/proj")
    assert not discovery.is_git_url("./proj")
    assert not discovery.is_git_url("proj")


def test_resolve_target_local(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    with discovery.resolve_target(str(repo)) as p:
        assert p == repo.resolve()


def test_resolve_target_rejects_non_git(tmp_path: Path):
    (tmp_path / "plain").mkdir()
    with pytest.raises(RuntimeError, match="not a git repository"):
        with discovery.resolve_target(str(tmp_path / "plain")):
            pass


def test_resolve_target_rejects_missing(tmp_path: Path):
    with pytest.raises(NotADirectoryError):
        with discovery.resolve_target(str(tmp_path / "nope")):
            pass


def test_list_tracked_files(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    files = sorted(discovery.list_tracked_files(repo))
    assert files == ["a.py", "b.py", "c/d.py"]
