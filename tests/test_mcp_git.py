"""Tests for :mod:`hotspottriage.mcp_git`."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from hotspottriage.mcp_git import git_live_head_and_branch, git_short_object_name


def test_git_short_object_name_empty_returns_none(tmp_path: Path) -> None:
    assert git_short_object_name(tmp_path, "  ") is None


def test_git_short_object_name_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    proc = MagicMock()
    proc.returncode = 0
    proc.stdout = "abc1234\n"

    def fake_run(*_a, **_k):
        return proc

    monkeypatch.setattr("hotspottriage.mcp_git.subprocess.run", fake_run)
    assert git_short_object_name(tmp_path, "deadbeef") == "abc1234"


def test_git_live_head_and_branch_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, **_k):
        calls.append(list(cmd))
        m = MagicMock()
        m.returncode = 0
        if "branch" in cmd:
            m.stdout = "main\n"
        else:
            m.stdout = "abc\n"
        return m

    monkeypatch.setattr("hotspottriage.mcp_git.subprocess.run", fake_run)
    head, br = git_live_head_and_branch(tmp_path)
    assert head == "abc"
    assert br == "main"


def test_git_live_head_and_branch_detached(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_run(cmd, **_k):
        m = MagicMock()
        m.returncode = 0
        if "branch" in cmd:
            m.stdout = "\n"
        else:
            m.stdout = "det1\n"
        return m

    monkeypatch.setattr("hotspottriage.mcp_git.subprocess.run", fake_run)
    head, br = git_live_head_and_branch(tmp_path)
    assert head == "det1"
    assert br == "detached"
