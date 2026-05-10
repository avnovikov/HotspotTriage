"""Tests for :mod:`hotspottriage.mcp.init_paths`."""

from pathlib import Path

from hotspottriage.mcp.init_paths import paths_written_as_str_list


def test_paths_written_as_str_list_single() -> None:
    assert paths_written_as_str_list(Path("/tmp/x")) == ["/tmp/x"]


def test_paths_written_as_str_list_iterable(tmp_path: Path) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    assert paths_written_as_str_list([a, b]) == [str(a), str(b)]
