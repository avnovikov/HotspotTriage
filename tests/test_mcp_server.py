"""Tests for the FastMCP server."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hotspottriage.mcp_server import (
    analyze,
    analyze_classes,
    generate_cache,
    analyze_with_cache,
    get_code_smells,
    cache_status,
    clear_cache,
    init_config,
    _effective_dashboard_config,
    _mcp_lifespan,
)


@pytest.fixture
def test_repo(tmp_path):
    """Create a simple test git repo."""
    import subprocess

    repo = tmp_path / "test_repo"
    repo.mkdir()

    # Initialize git repo
    subprocess.run(
        ["git", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    # Create a simple Python file
    py_file = repo / "example.py"
    py_file.write_text(
        """
def simple_function(x):
    if x > 0:
        return x * 2
    else:
        return x / 2

def complex_function(a, b, c):
    if a > 0:
        if b > 0:
            if c > 0:
                return a + b + c
            else:
                return a + b
        else:
            return a
    else:
        return 0
"""
    )

    # Commit the file
    subprocess.run(
        ["git", "add", "example.py"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    return repo


def test_analyze_basic(test_repo):
    """Test basic analyze functionality."""
    result = analyze(str(test_repo))
    data = json.loads(result)

    # Should return a list of statistics
    assert isinstance(data, list)
    assert len(data) > 0

    # Check minimal structure of first result
    first = data[0]
    assert "score" in first
    assert "score_band" in first
    assert set(first.keys()) == {"score", "score_band"}


def test_analyze_with_limit(test_repo):
    """Test analyze with limit."""
    result = analyze(str(test_repo), limit=1)
    data = json.loads(result)

    # Should respect limit
    assert len(data) <= 1


def test_analyze_with_score_metrics(test_repo):
    """Test analyze with custom score metrics."""
    result = analyze(
        str(test_repo),
        score_metrics="cyclomatic",
    )
    data = json.loads(result)

    # Should return results with custom score
    assert len(data) > 0
    assert "score" in data[0]


def test_analyze_with_granularity_block(test_repo):
    """Test analyze with block granularity (per-function)."""
    result = analyze(
        str(test_repo),
        granularity="block",
        score_metrics="cyclomatic",
    )
    data = json.loads(result)

    # With block granularity, we should get multiple rows per file
    # (one per function)
    assert len(data) >= 2  # We defined 2 functions in test_repo


def test_analyze_error_handling():
    """Test error handling for invalid repo."""
    result = analyze("/nonexistent/path")
    data = json.loads(result)

    # Should return error object
    assert "error" in data


def test_analyze_with_filter(test_repo):
    """Test analyze with glob filter."""
    result = analyze(
        str(test_repo),
        filter="**/*.py",
    )
    data = json.loads(result)

    # Should return results
    assert len(data) > 0


def test_init_config_project(test_repo):
    """Test project config initialization."""
    result = init_config(str(test_repo), is_global=False)
    data = json.loads(result)

    # Should return success
    assert data["status"] == "success"
    assert "files" in data
    assert len(data["files"]) > 0

    # Files should be created
    config_dir = test_repo / ".hotspottriage"
    assert config_dir.exists()


def test_init_config_global():
    """Test global config initialization.

    Note: This test will succeed if global config exists (as expected
    in development), or fail gracefully if the directory is not writable.
    """
    result = init_config(is_global=True)
    data = json.loads(result)

    # Should either succeed or fail with a clear error message
    # (not crash unexpectedly)
    assert isinstance(data, dict)
    assert "status" in data
    assert data["status"] in ("success", "error")

    # If it's an error, it should be because config already exists
    if data["status"] == "error":
        assert "already exists" in data["message"] or "refusing" in data["message"]


def test_analyze_sort_by_file(test_repo):
    """Test analyze sorting by file."""
    result = analyze(str(test_repo), sort="file")
    data = json.loads(result)

    # Should return results sorted by file path
    assert len(data) > 0
    # Can't guarantee much more about sorting without knowing the exact files


def test_cache_status_empty(test_repo):
    """Test cache status for repo without cache."""
    result = cache_status(str(test_repo))
    data = json.loads(result)

    assert data["status"] in ("empty", "ok")
    assert "cache_dir" in data
    assert "entries" in data


def test_clear_cache(test_repo):
    """Test clearing cache."""
    # First generate some cache
    analyze_with_cache(str(test_repo))

    # Then clear it
    result = clear_cache(str(test_repo))
    data = json.loads(result)

    assert data["status"] == "success"

    # Verify cache is cleared
    status_result = cache_status(str(test_repo))
    status = json.loads(status_result)
    assert status["entries"] == 0


def test_analyze_with_cache(test_repo):
    """Test cache-backed analysis with block granularity."""
    result = analyze_with_cache(str(test_repo), score_metrics="cyclomatic")
    data = json.loads(result)

    # Should have results and cache info
    assert "results" in data
    assert "cache" in data
    assert "entries" in data["cache"]
    assert len(data["results"]) > 0
    assert "normalized_sloc" in data["results"][0]
    assert "score" in data["results"][0]
    assert "score_band" in data["results"][0]


def test_analyze_classes(test_repo):
    """Test class and method analysis."""
    result = analyze_classes(str(test_repo))
    data = json.loads(result)

    # Should return list of classes/methods
    assert isinstance(data, list)
    assert len(data) > 0

    # Check structure
    for item in data:
        assert "file" in item
        assert "full_name" in item
        assert "start_line" in item
        assert "end_line" in item
        assert "lines" in item


def test_analyze_classes_with_filter(test_repo):
    """Test class analysis with glob filter."""
    result = analyze_classes(str(test_repo), filter="**/*.py")
    data = json.loads(result)

    # Should return results
    assert isinstance(data, list)
    assert len(data) > 0


def test_generate_cache_includes_normalized_sloc_in_block_results(test_repo):
    """Comprehensive cache output should retain block metric fields."""
    result = generate_cache(str(test_repo), score_metrics="cyclomatic")
    data = json.loads(result)
    assert data.get("metadata", {}).get("status") == "success"
    blocks = data.get("blocks", {})
    assert blocks.get("count", 0) > 0
    assert "results" in blocks
    assert "normalized_sloc" in blocks["results"][0]


def test_get_code_smells_returns_smell_rows(test_repo):
    result = get_code_smells(str(test_repo))
    data = json.loads(result)
    assert isinstance(data, list)
    if data:
        first = data[0]
        assert "file" in first
        assert "line" in first
        assert "smell" in first
        assert "message" in first


def test_effective_dashboard_config_uses_cli_overrides(monkeypatch):
    from argparse import Namespace
    import hotspottriage.mcp_server as mcp_mod

    monkeypatch.setattr(
        mcp_mod,
        "_mcp_dashboard_cli",
        Namespace(
            no_dashboard=True,
            dashboard_port=9333,
            dashboard_host="0.0.0.0",
            open_browser=True,
        ),
    )
    cfg = _effective_dashboard_config()
    dash = cfg["dashboard"]
    assert dash["enabled"] is False
    assert dash["base_port"] == 9333
    assert dash["host"] == "0.0.0.0"
    assert dash["open_on_start"] is True


@pytest.mark.anyio
async def test_mcp_lifespan_dashboard_failure_is_non_fatal(monkeypatch):
    import hotspottriage.mcp_server as mcp_mod

    class _Boom:
        def __init__(self, **_: object) -> None:
            raise OSError("no free ports")

    monkeypatch.setattr(mcp_mod, "DashboardServer", _Boom)
    async with _mcp_lifespan(None):
        assert True
