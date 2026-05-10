"""Tests for detached worktree helpers used by MCP ``analyze``."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from hotspottriage.git_rev_worktree import detached_worktree, resolve_rev


@pytest.fixture
def tiny_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "r"
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


def test_resolve_rev_head(tiny_repo: Path) -> None:
    sha = resolve_rev(tiny_repo, "HEAD")
    assert len(sha) == 40


def test_resolve_rev_invalid(tiny_repo: Path) -> None:
    with pytest.raises(ValueError, match="invalid git rev"):
        resolve_rev(tiny_repo, "does-not-exist-zzzz")


def test_detached_worktree_materializes_old_commit(tiny_repo: Path) -> None:
    old = resolve_rev(tiny_repo, "HEAD~1")
    with detached_worktree(tiny_repo, "HEAD~1") as wt:
        text = (wt / "a.py").read_text()
        assert "def only()" in text
        assert "def second()" not in text
    proc = subprocess.run(
        ["git", "-C", str(tiny_repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert proc.stdout.strip() != old
