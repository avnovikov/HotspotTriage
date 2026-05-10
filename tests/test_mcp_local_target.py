"""Tests for :mod:`hotspottriage.mcp.local_target`."""

import json
from pathlib import Path

from hotspottriage.mcp.local_target import local_repo_path_or_error


def test_local_repo_path_or_error_accepts_path(tmp_path) -> None:
    p = tmp_path / "repo"
    p.mkdir()
    out = local_repo_path_or_error(
        str(p),
        tool="cache_status",
        remote_message="no remote",
    )
    assert isinstance(out, Path)
    assert out.resolve() == p.resolve()


def test_local_repo_path_or_error_rejects_remote() -> None:
    out = local_repo_path_or_error(
        "https://example.com/a.git",
        tool="clear_cache",
        remote_message="must be local",
    )
    assert isinstance(out, str)
    data = json.loads(out)
    assert "error" in data
    assert data["error"]["code"] == "INVALID_TARGET"
