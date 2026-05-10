"""Tests for :mod:`hotspottriage.mcp.repo_filter`."""

from pathlib import Path

from hotspottriage.mcp.repo_filter import build_repo_keep_predicate


def test_build_repo_keep_predicate_literal_or_two_files(
    tiny_git_repo_with_two_py_files: Path,
) -> None:
    cfg = {
        "filter": ["example.py", "other.py"],
        "no_default_filter": True,
        "default_filter": "**/*.py",
        "ignore_directories": [],
        "respect_gitignore": True,
    }
    keep = build_repo_keep_predicate(tiny_git_repo_with_two_py_files, cfg)
    assert keep("example.py") is True
    assert keep("missing.py") is False
