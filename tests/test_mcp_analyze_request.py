"""Tests for :mod:`hotspottriage.mcp.analyze_request`."""

from hotspottriage.mcp.analyze_request import AnalyzeRequest


def test_analyze_request_from_tool_kwargs_maps_filter() -> None:
    r = AnalyzeRequest.from_tool_kwargs(
        "/repo",
        filter="a.py,b.py",
        limit=5,
        compact=False,
        before_sha="abc",
    )
    assert r.target == "/repo"
    assert r.path_filter == "a.py,b.py"
    assert r.limit == 5
    assert r.compact is False
    assert r.before_sha == "abc"
    assert r.progress_callback is None
