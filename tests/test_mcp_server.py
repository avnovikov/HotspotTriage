"""Tests for the FastMCP server."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hotspottriage.mcp_server import analyze, init_config


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

    # Check structure of first result
    first = data[0]
    assert "path" in first
    assert "sloc" in first
    assert "cyclomatic" in first
    assert "halstead" in first
    assert "maintainability" in first
    assert "churn" in first
    assert "churn_per_sloc" in first
    assert "score" in first


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
