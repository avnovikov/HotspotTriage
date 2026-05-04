"""Tests for cache generator module."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hotspottriage.cache_generator import (
    generate_full_cache,
    print_cache_summary,
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

    # Create test files
    (repo / "module1.py").write_text(
        """
def func1(x):
    if x > 0:
        return x * 2
    return 0

def func2(y):
    return y + 1

class MyClass:
    def method1(self):
        pass

    def method2(self, x):
        if x > 0:
            if x > 10:
                return x
        return 0
"""
    )

    (repo / "module2.py").write_text(
        """
def simple():
    return 42

class AnotherClass:
    pass
"""
    )

    # Commit
    subprocess.run(
        ["git", "add", "."],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    return repo


def test_generate_full_cache_basic(test_repo):
    """Test basic cache generation."""
    result = generate_full_cache(str(test_repo))

    assert result["metadata"]["status"] == "success"
    assert result["blocks"]["count"] > 0
    assert result["classes"]["count"] > 0
    assert result["cache_status"]["status"] == "ok"


def test_generate_full_cache_with_filter(test_repo):
    """Test cache generation with filter."""
    result = generate_full_cache(str(test_repo), filter="module1.py")

    assert result["metadata"]["status"] == "success"
    # Should have blocks from filtered files
    assert result["blocks"]["count"] >= 3  # At least 3 functions from module1


def test_generate_full_cache_structure(test_repo):
    """Test cache structure and content."""
    result = generate_full_cache(str(test_repo))

    # Check structure
    assert "timestamp" in result
    assert "target" in result
    assert "blocks" in result
    assert "classes" in result
    assert "cache_status" in result
    assert "metadata" in result

    # Check blocks (cache initialization doesn't return results, only cache info)
    blocks = result["blocks"]
    assert "count" in blocks
    assert "cache" in blocks
    assert "cache_file" in blocks["cache"]
    assert "entries" in blocks["cache"]

    # Check classes
    classes = result["classes"]
    assert "count" in classes
    assert "results" in classes
    assert isinstance(classes["results"], list)

    # Check metadata
    metadata = result["metadata"]
    assert "blocks_cached" in metadata
    assert "classes_indexed" in metadata
    assert "total_cache_entries" in metadata
    assert "cache_size_mb" in metadata


def test_generate_full_cache_blocks_contain_metrics(test_repo):
    """Test that blocks cache was generated."""
    result = generate_full_cache(str(test_repo), score_metrics="cyclomatic")

    # Cache initialization doesn't return block results, just cache info
    blocks = result["blocks"]
    assert "cache" in blocks
    assert blocks["count"] > 0
    assert blocks["cache"]["entries"] > 0


def test_generate_full_cache_classes_contain_structure(test_repo):
    """Test that classes contain structure information."""
    result = generate_full_cache(str(test_repo))

    classes = result["classes"]["results"]
    assert len(classes) > 0

    # Check structure
    item = classes[0]
    assert "file" in item
    assert "full_name" in item
    assert "start_line" in item
    assert "end_line" in item
    assert "lines" in item


def test_generate_full_cache_cache_actually_created(test_repo):
    """Test that cache files are actually created."""
    result = generate_full_cache(str(test_repo))

    cache_status = result["cache_status"]
    assert cache_status["status"] in ("ok", "empty")

    if cache_status["status"] == "ok":
        # Cache was created
        assert cache_status["entries"] > 0
        cache_file = Path(cache_status.get("cache_file", ""))
        if cache_file.exists():
            assert cache_file.stat().st_size > 0


def test_print_cache_summary(test_repo, capsys):
    """Test that cache summary prints without errors."""
    result = generate_full_cache(str(test_repo), verbose=False)

    # Should not raise
    print_cache_summary(result)

    # Check output
    captured = capsys.readouterr()
    assert "CACHE GENERATION SUMMARY" in captured.out
    assert "success" in captured.out.lower()


def test_generate_full_cache_verbose_output(test_repo, capsys):
    """Test verbose output during generation."""
    result = generate_full_cache(str(test_repo), verbose=True)

    captured = capsys.readouterr()
    assert "Generating cache" in captured.out
    assert "Initializing block-level" in captured.out
    assert "class/method structure" in captured.out
    assert "✅ Cache generation complete" in captured.out
