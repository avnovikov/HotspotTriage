"""Tests for :mod:`hotspottriage.mcp.target`."""

import pytest

from hotspottriage.mcp.target import resolve_mcp_target


def test_resolve_mcp_target_explicit_wins():
    assert resolve_mcp_target("  /repo  ", default_target="/default") == "/repo"


def test_resolve_mcp_target_falls_back_to_default():
    assert resolve_mcp_target("", default_target="/default") == "/default"
    assert resolve_mcp_target("   ", default_target="/default") == "/default"


def test_resolve_mcp_target_requires_target_or_default():
    with pytest.raises(ValueError, match="non-empty target"):
        resolve_mcp_target("", default_target=None)
    with pytest.raises(ValueError, match="non-empty target"):
        resolve_mcp_target("", default_target="")
