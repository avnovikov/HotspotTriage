"""Tests for :mod:`hotspottriage.mcp_filter_paths`."""

from hotspottriage.mcp_filter_paths import (
    effective_mcp_filter_patterns,
    is_literal_filter_path,
    normalize_filter_path,
)


def test_is_literal_filter_path() -> None:
    assert is_literal_filter_path("src/a.py") is True
    assert is_literal_filter_path("src/*.py") is False
    assert is_literal_filter_path("") is False
    assert is_literal_filter_path("!x") is False


def test_normalize_filter_path_delegates() -> None:
    assert normalize_filter_path("./x/y.py") == "x/y.py"


def test_effective_mcp_filter_patterns_literal_or() -> None:
    cfg = {
        "filter": ["a.py", "b.py"],
        "no_default_filter": False,
        "default_filter": "**/*.py",
    }
    assert effective_mcp_filter_patterns(cfg) == ["a.py", "b.py"]


def test_effective_mcp_filter_patterns_appends_default() -> None:
    cfg = {
        "filter": ["src/**/*.py"],
        "no_default_filter": False,
        "default_filter": "**/*.py",
    }
    out = effective_mcp_filter_patterns(cfg)
    assert out[0] == "src/**/*.py"
    assert "**/*.py" in out
