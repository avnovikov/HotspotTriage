"""Tests for the FastMCP server."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from hotspottriage import config as _config
from hotspottriage.mcp_server import (
    analyze,
    generate_cache,
    cache_status,
    clear_cache,
    init_config,
    _effective_dashboard_config,
    _ensure_root_logging_configured,
    _mcp_lifespan,
)


@pytest.fixture(autouse=True)
def _no_pylint_smells(monkeypatch):
    """Tests run without requiring a pylint executable on PATH."""
    monkeypatch.setattr(
        "hotspottriage.smell.compute_smells",
        lambda *args, **kwargs: [],
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

    helper_file = repo / "helper.py"
    helper_file.write_text(
        """
def helper_branch(x):
    if x % 2 == 0:
        return "even"
    return "odd"
"""
    )

    # Commit the file
    subprocess.run(
        ["git", "add", "example.py", "helper.py"],
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
    """Test basic analyze functionality (full rows)."""
    result = analyze(str(test_repo), compact=False)
    data = json.loads(result)

    assert "results" in data and "cache" in data
    rows = data["results"]
    assert isinstance(rows, list)
    assert len(rows) > 0

    first = rows[0]
    assert "path" in first
    assert "sloc" in first
    assert "normalized_sloc" in first
    assert "cyclomatic" in first
    assert "halstead" in first
    assert "maintainability" in first
    assert "churn" in first
    assert "churn_per_sloc" in first
    assert "smell_count" in first
    assert "smell_severity" in first
    assert "smell_burden" in first
    assert "smells" in first
    assert "similarity_score" in first
    assert "similarity_band" in first
    assert "match_count" in first
    assert "score" in first
    assert "score_band" in first
    assert "score_subscores" in first
    assert "norm_cyclomatic" in first
    assert "norm_similarity_score" in first


def test_analyze_with_limit(test_repo):
    """Test analyze with limit (non-aggregate rows only; limit excludes similarity summary)."""
    result = analyze(str(test_repo), limit=1, similarity=False)
    data = json.loads(result)

    assert len(data["results"]) <= 1


def test_analyze_with_score_metrics(test_repo):
    """Test analyze with custom score metrics."""
    result = analyze(
        str(test_repo),
        score_metrics="cyclomatic",
        compact=False,
    )
    data = json.loads(result)

    assert len(data["results"]) > 0
    assert "score" in data["results"][0]


def test_analyze_returns_multiple_blocks(test_repo):
    """Block analysis yields one row per function."""
    result = analyze(
        str(test_repo),
        score_metrics="cyclomatic",
        compact=False,
    )
    data = json.loads(result)

    assert len(data["results"]) >= 2


def test_analyze_error_handling():
    """Test error handling for invalid repo."""
    result = analyze("/nonexistent/path")
    data = json.loads(result)

    assert "error" in data


def test_analyze_with_filter(test_repo):
    """Test analyze with glob filter."""
    result = analyze(
        str(test_repo),
        filter="**/*.py",
        compact=False,
    )
    data = json.loads(result)

    assert len(data["results"]) > 0


def test_analyze_with_multiple_literal_file_filters_returns_union(test_repo):
    """Multiple literal file paths in MCP filter should include each file."""
    result = analyze(
        str(test_repo),
        filter="example.py,helper.py",
        compact=False,
        similarity=False,
    )
    data = json.loads(result)
    result_paths = {row["path"].split("::", 1)[0] for row in data["results"]}

    assert "example.py" in result_paths
    assert "helper.py" in result_paths


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
    result = analyze(str(test_repo), sort="file", compact=False)
    data = json.loads(result)

    assert len(data["results"]) > 0


def test_cache_status_empty(test_repo):
    """Test cache status for repo without cache."""
    result = cache_status(str(test_repo))
    data = json.loads(result)

    assert data["status"] in ("empty", "ok")
    assert "cache_dir" in data
    assert "entries" in data


def test_clear_cache(test_repo):
    """Test clearing cache."""
    analyze(str(test_repo), compact=False)

    result = clear_cache(str(test_repo))
    data = json.loads(result)

    assert data["status"] == "success"

    status_result = cache_status(str(test_repo))
    status = json.loads(status_result)
    assert status["entries"] == 0


def test_analyze_returns_cache_metadata(test_repo):
    """Cache-backed analyze includes cache stats."""
    result = analyze(str(test_repo), score_metrics="cyclomatic", compact=False)
    data = json.loads(result)

    assert "results" in data
    assert "cache" in data
    assert "entries" in data["cache"]
    assert len(data["results"]) > 0
    assert "normalized_sloc" in data["results"][0]


def test_generate_cache_includes_normalized_sloc_in_block_results(test_repo):
    """Comprehensive cache output should retain block metric fields."""
    result = generate_cache(str(test_repo), score_metrics="cyclomatic")
    data = json.loads(result)
    assert data.get("metadata", {}).get("status") == "success"
    blocks = data.get("blocks", {})
    assert blocks.get("count", 0) > 0
    assert "results" in blocks
    assert "normalized_sloc" in blocks["results"][0]


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


def test_analyze_compact_default_returns_function_score_risk_band_and_model(monkeypatch, test_repo):
    monkeypatch.setattr(
        "hotspottriage.smell.compute_smells",
        lambda *args, **kwargs: [],
    )
    result = analyze(
        str(test_repo),
        score_metrics="cyclomatic",
    )
    data = json.loads(result)
    assert "results" in data
    rows = data["results"]
    assert isinstance(rows, list) and len(rows) >= 1
    first = rows[0]
    assert set(first.keys()) == {"function", "score", "risk_band", "proposed_model"}
    assert isinstance(first["function"], str)
    assert isinstance(first["score"], float)
    assert isinstance(first["risk_band"], str)
    assert isinstance(first["proposed_model"], str)


def test_analyze_compact_uses_configured_proposed_models(monkeypatch, test_repo):
    monkeypatch.setattr(
        "hotspottriage.smell.compute_smells",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setitem(
        _config.DEFAULTS,
        "proposed_models",
        {
            "low": "gpt-4o-mini",
            "medium": "gpt-4.1",
            "high": "o3",
            "critical": "o3-pro",
        },
    )

    result = analyze(str(test_repo), score_metrics="cyclomatic")
    data = json.loads(result)
    rows = data["results"]
    assert rows
    expected_by_band = {
        "low": "gpt-4o-mini",
        "medium": "gpt-4.1",
        "high": "o3",
        "critical": "o3-pro",
    }
    for row in rows:
        risk_band = row["risk_band"]
        if risk_band in expected_by_band:
            assert row["proposed_model"] == expected_by_band[risk_band]
        else:
            assert row["proposed_model"] == ""


def test_analyze_uses_project_config_proposed_models(test_repo):
    config_dir = test_repo / ".hotspottriage"
    config_dir.mkdir(exist_ok=True)
    (config_dir / "project.yml").write_text(
        """
proposed_models:
  low: local-low
  medium: local-medium
  high: local-high
  critical: local-critical
""".strip()
    )
    result = analyze(str(test_repo))
    data = json.loads(result)
    rows = data["results"]
    assert rows
    expected_by_band = {
        "low": "local-low",
        "medium": "local-medium",
        "high": "local-high",
        "critical": "local-critical",
    }
    for row in rows:
        risk_band = row["risk_band"]
        if risk_band in expected_by_band:
            assert row["proposed_model"] == expected_by_band[risk_band]


def test_analyze_uses_dashboard_patch_proposed_models(test_repo):
    config_dir = test_repo / ".hotspottriage"
    config_dir.mkdir(exist_ok=True)
    (config_dir / "dashboard_config_patch.yml").write_text(
        """
proposed_models:
  low: ui-low
  medium: ui-medium
  high: ui-high
  critical: ui-critical
""".strip()
    )
    result = analyze(str(test_repo))
    data = json.loads(result)
    rows = data["results"]
    assert rows
    expected_by_band = {
        "low": "ui-low",
        "medium": "ui-medium",
        "high": "ui-high",
        "critical": "ui-critical",
    }
    for row in rows:
        risk_band = row["risk_band"]
        if risk_band in expected_by_band:
            assert row["proposed_model"] == expected_by_band[risk_band]


def test_ensure_root_logging_configured_lowers_warning_threshold():
    root = logging.getLogger()
    previous_level = root.level
    try:
        root.setLevel(logging.WARNING)
        _ensure_root_logging_configured()
        assert root.level <= logging.INFO
    finally:
        root.setLevel(previous_level)


def test_analyze_block_publishes_rows_to_dashboard(monkeypatch, test_repo):
    import hotspottriage.mcp_server as mcp_mod

    monkeypatch.setattr(
        "hotspottriage.smell.compute_smells",
        lambda *args, **kwargs: [],
    )

    class _Capturing:
        def __init__(self) -> None:
            self.rows = None

        def publish_latest_block_metrics(self, rows):
            self.rows = rows

    cap = _Capturing()
    monkeypatch.setattr(mcp_mod, "_dashboard_server_instance", cap)
    result = analyze(str(test_repo), score_metrics="cyclomatic", compact=False)
    data = json.loads(result)
    assert "results" in data
    assert cap.rows is not None
    assert len(cap.rows) >= 2


def test_analyze_publishes_before_limit(monkeypatch, test_repo):
    import hotspottriage.mcp_server as mcp_mod

    monkeypatch.setattr(
        "hotspottriage.smell.compute_smells",
        lambda *args, **kwargs: [],
    )

    captured: dict[str, object] = {}

    class _Capturing:
        def publish_latest_block_metrics(self, rows):
            captured["rows"] = rows

    monkeypatch.setattr(mcp_mod, "_dashboard_server_instance", _Capturing())
    out = analyze(str(test_repo), score_metrics="cyclomatic", limit=1, compact=False)
    data = json.loads(out)
    assert "results" in data
    rows = captured.get("rows")
    assert rows is not None
    assert isinstance(rows, list)
    assert len(rows) >= 2
    assert len(data["results"]) <= len(rows)


def test_analyze_empty_target_uses_default_target(monkeypatch, test_repo):
    import hotspottriage.mcp_server as mcp_mod

    monkeypatch.setattr(mcp_mod, "_mcp_default_target", str(test_repo))
    monkeypatch.setattr(
        "hotspottriage.smell.compute_smells",
        lambda *args, **kwargs: [],
    )
    result = analyze("")
    data = json.loads(result)
    assert "results" in data and "cache" in data


def test_analyze_empty_without_default_target_errors(monkeypatch):
    import hotspottriage.mcp_server as mcp_mod

    monkeypatch.setattr(mcp_mod, "_mcp_default_target", None)
    result = analyze("")
    data = json.loads(result)
    assert "error" in data
    assert "default-target" in data["error"].lower()


@pytest.mark.anyio
async def test_mcp_lifespan_dashboard_failure_is_non_fatal(monkeypatch):
    import hotspottriage.mcp_server as mcp_mod

    class _Boom:
        def __init__(self, **_: object) -> None:
            raise OSError("no free ports")

    monkeypatch.setattr(mcp_mod, "DashboardServer", _Boom)
    async with _mcp_lifespan(None):
        assert True


def test_analyze_filtered_dashboard_publish_excludes_other_cached_files(
    monkeypatch, test_repo
):
    """Scoped runs keep prior cache rows; dashboard publish must not restore them."""
    import hotspottriage.mcp_server as mcp_mod

    monkeypatch.setattr(
        "hotspottriage.smell.compute_smells",
        lambda *args, **kwargs: [],
    )

    publishes: list[list] = []

    class _Capturing:
        def publish_latest_block_metrics(self, rows):
            publishes.append(list(rows))

    monkeypatch.setattr(mcp_mod, "_dashboard_server_instance", _Capturing())

    analyze(str(test_repo), score_metrics="cyclomatic", compact=False, similarity=False)
    analyze(
        str(test_repo),
        filter="example.py",
        score_metrics="cyclomatic",
        compact=False,
        similarity=False,
    )

    assert publishes
    final = publishes[-1]
    files = {row["path"].split("::", 1)[0] for row in final}
    assert "example.py" in files
    assert "helper.py" not in files
