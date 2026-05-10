"""Tests for :mod:`hotspottriage.mcp.config_fingerprint`."""

from hotspottriage.mcp.config_fingerprint import config_fingerprint


def test_config_fingerprint_stable_and_order_independent() -> None:
    a = config_fingerprint({"z": 1, "a": 2})
    b = config_fingerprint({"a": 2, "z": 1})
    assert a == b
    assert a.startswith("sha256:")
