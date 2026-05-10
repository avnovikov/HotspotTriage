"""Tests for the FastMCP server."""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

import pytest

import hotspottriage.mcp_server as mcp_server
from hotspottriage import config as _config


def test_effective_similarity_helper_explicit_and_defaults() -> None:
    fn = mcp_server._effective_similarity_enabled_for_mcp_analyze
    assert fn(True, "a.py") is True
    assert fn(False, None) is False
    assert fn(None, None) is True
    assert fn(None, "") is True
    assert fn(None, "   ") is True
    assert fn(None, "x.py") is False
    assert fn(None, "**/*.py") is False


def test_mcp_analyze_filtered_defaults_similarity_off(monkeypatch, test_repo):
    captured: dict[str, bool | None] = {}
    _orig = mcp_server.stats.build_block_stats

    def _spy(repo, files, score_metrics, *a, **kw):
        captured["similarity_enabled"] = kw.get("similarity_enabled")
        return _orig(repo, files, score_metrics, *a, **kw)

    monkeypatch.setattr(mcp_server.stats, "build_block_stats", _spy)
    mcp_server.analyze(str(test_repo), filter="example.py", compact=True)
    assert captured["similarity_enabled"] is False


def test_mcp_analyze_unfiltered_defaults_similarity_on(monkeypatch, test_repo):
    captured: dict[str, bool | None] = {}
    _orig = mcp_server.stats.build_block_stats

    def _spy(repo, files, score_metrics, *a, **kw):
        captured["similarity_enabled"] = kw.get("similarity_enabled")
        return _orig(repo, files, score_metrics, *a, **kw)

    monkeypatch.setattr(mcp_server.stats, "build_block_stats", _spy)
    mcp_server.analyze(str(test_repo), compact=True)
    assert captured["similarity_enabled"] is True


def test_mcp_analyze_filtered_explicit_similarity_true(monkeypatch, test_repo):
    captured: dict[str, bool | None] = {}
    _orig = mcp_server.stats.build_block_stats

    def _spy(repo, files, score_metrics, *a, **kw):
        captured["similarity_enabled"] = kw.get("similarity_enabled")
        return _orig(repo, files, score_metrics, *a, **kw)

    monkeypatch.setattr(mcp_server.stats, "build_block_stats", _spy)
    mcp_server.analyze(
        str(test_repo), filter="example.py", compact=True, similarity=True
    )
    assert captured["similarity_enabled"] is True


def test_build_analyze_config_local_matches_load_analyze_for_scoring(test_repo):
    """MCP local analyze must use the same scoring layers as ``load_analyze_config_for_local_repo``."""
    cfg = mcp_server._build_analyze_config(str(test_repo))
    want = _config.load_analyze_config_for_local_repo(Path(test_repo))
    assert cfg["metric_normalization"] == want["metric_normalization"]
    assert cfg["score_aggregation"] == want["score_aggregation"]
    assert cfg.get("proposed_models") == want.get("proposed_models")


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
    result = mcp_server.analyze(str(test_repo), compact=False)
    data = json.loads(result)

    assert "metadata" in data
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
    assert "score_driver" in first
    assert "score_explanation" in first
    assert "score_narrative" in first
    assert "norm_cyclomatic" in first
    assert "norm_similarity_score" in first


def test_analyze_compact_includes_rationale_fields(test_repo):
    result = mcp_server.analyze(str(test_repo), compact=True)
    data = json.loads(result)
    row = data["results"][0]
    assert "rationale" in row
    assert "score_driver" in row
    assert isinstance(row.get("rationale"), str)
    assert "Main driver:" in row["rationale"]


def test_analyze_compact_rows_never_include_score_explanation_or_narrative(test_repo):
    """Contract: triage (compact) rows stay small—no embedded explanation blobs."""
    result = mcp_server.analyze(str(test_repo), compact=True)
    data = json.loads(result)
    for row in data["results"]:
        assert "score_explanation" not in row
        assert "score_narrative" not in row
        assert "path" not in row


def test_analyze_full_rows_score_explanation_items_never_contain_raw(test_repo):
    """Contract: full-mode score_explanation must not expose legacy raw counters."""
    result = mcp_server.analyze(str(test_repo), compact=False)
    data = json.loads(result)
    for row in data["results"]:
        expl = row.get("score_explanation")
        if not expl:
            continue
        if isinstance(expl, str):
            expl = json.loads(expl)
        for item in expl:
            assert isinstance(item, dict)
            assert "raw" not in item
def test_analyze_with_limit(test_repo):
    """Test analyze with limit (non-aggregate rows only; limit excludes similarity summary)."""
    result = mcp_server.analyze(str(test_repo), limit=1, similarity=False)
    data = json.loads(result)

    assert len(data["results"]) <= 1


def test_analyze_with_score_metrics(test_repo):
    """Test analyze with custom score metrics."""
    result = mcp_server.analyze(
        str(test_repo),
        score_metrics="cyclomatic",
        compact=False,
    )
    data = json.loads(result)

    assert len(data["results"]) > 0
    assert "score" in data["results"][0]


def test_analyze_returns_multiple_blocks(test_repo):
    """Block analysis yields one row per function."""
    result = mcp_server.analyze(
        str(test_repo),
        score_metrics="cyclomatic",
        compact=False,
    )
    data = json.loads(result)

    assert len(data["results"]) >= 2


def test_analyze_error_handling():
    """Test error handling for invalid repo."""
    result = mcp_server.analyze("/nonexistent/path")
    data = json.loads(result)

    assert "error" in data


def test_analyze_with_filter(test_repo):
    """Test analyze with glob filter."""
    result = mcp_server.analyze(
        str(test_repo),
        filter="**/*.py",
        compact=False,
    )
    data = json.loads(result)

    assert len(data["results"]) > 0


def test_analyze_with_multiple_literal_file_filters_returns_union(test_repo):
    """Multiple literal file paths in MCP filter should include each file."""
    result = mcp_server.analyze(
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
    result = mcp_server.init_config(str(test_repo), is_global=False)
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
    result = mcp_server.init_config(is_global=True)
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
    result = mcp_server.analyze(str(test_repo), sort="file", compact=False)
    data = json.loads(result)

    assert len(data["results"]) > 0


def test_cache_status_empty(test_repo):
    """Test cache status for repo without cache."""
    result = mcp_server.cache_status(str(test_repo))
    data = json.loads(result)

    assert data["status"] in ("empty", "ok")
    assert "cache_dir" in data
    assert "entries" in data


def test_clear_cache(test_repo):
    """Test clearing cache."""
    mcp_server.analyze(str(test_repo), compact=False)

    result = mcp_server.clear_cache(str(test_repo))
    data = json.loads(result)

    assert data["status"] == "success"

    status_result = mcp_server.cache_status(str(test_repo))
    status = json.loads(status_result)
    assert status["entries"] == 0


def test_analyze_returns_cache_metadata(test_repo):
    """Cache-backed analyze includes cache stats."""
    result = mcp_server.analyze(str(test_repo), score_metrics="cyclomatic", compact=False)
    data = json.loads(result)

    assert "results" in data
    assert "cache" in data
    assert "entries" in data["cache"]
    assert len(data["results"]) > 0
    assert "normalized_sloc" in data["results"][0]


def test_generate_cache_includes_normalized_sloc_in_block_results(test_repo):
    """Comprehensive cache output should retain block metric fields."""
    result = mcp_server.generate_cache(str(test_repo), score_metrics="cyclomatic")
    data = json.loads(result)
    assert data.get("metadata", {}).get("status") == "success"
    blocks = data.get("blocks", {})
    assert blocks.get("count", 0) > 0
    assert "results" in blocks
    assert "normalized_sloc" in blocks["results"][0]


def test_effective_dashboard_config_uses_cli_overrides(monkeypatch):
    from argparse import Namespace

    monkeypatch.setattr(
        mcp_server,
        "_mcp_dashboard_cli",
        Namespace(
            no_dashboard=True,
            dashboard_port=9333,
            dashboard_host="0.0.0.0",
            open_browser=True,
        ),
    )
    cfg = mcp_server._effective_dashboard_config()
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
    result = mcp_server.analyze(
        str(test_repo),
        score_metrics="cyclomatic",
    )
    data = json.loads(result)
    assert "results" in data
    rows = data["results"]
    assert isinstance(rows, list) and len(rows) >= 1
    first = rows[0]
    assert set(first.keys()) == {
        "file",
        "function",
        "score",
        "risk_band",
        "proposed_model",
        "score_driver",
        "rationale",
    }
    assert isinstance(first["file"], str)
    assert isinstance(first["function"], str)
    assert isinstance(first["score"], float)
    assert isinstance(first["risk_band"], str)
    assert isinstance(first["proposed_model"], str)
    assert isinstance(first["score_driver"], str)
    assert isinstance(first["rationale"], str)


def test_analyze_compact_file_key_holds_originating_file_in_block_mode(test_repo):
    """Compact rows expose ``file`` so agents can edit without re-running with compact=false."""
    result = mcp_server.analyze(str(test_repo), score_metrics="cyclomatic")
    data = json.loads(result)
    block_rows = [r for r in data["results"] if not r["file"].startswith("__")]
    assert block_rows
    assert {row["file"] for row in block_rows} <= {"example.py", "helper.py"}
    for row in block_rows:
        assert "::" not in row["file"]
        assert "::" not in row["function"]


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

    result = mcp_server.analyze(str(test_repo), score_metrics="cyclomatic")
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
    result = mcp_server.analyze(str(test_repo))
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
    result = mcp_server.analyze(str(test_repo))
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
        mcp_server._ensure_root_logging_configured()
        assert root.level <= logging.INFO
    finally:
        root.setLevel(previous_level)


def test_analyze_block_publishes_rows_to_dashboard(monkeypatch, test_repo):
    monkeypatch.setattr(
        "hotspottriage.smell.compute_smells",
        lambda *args, **kwargs: [],
    )

    class _Capturing:
        def __init__(self) -> None:
            self.rows = None

        def publish_latest_block_metrics(self, rows, **kwargs):
            self.rows = rows

    cap = _Capturing()
    monkeypatch.setattr(mcp_server, "_dashboard_server_instance", cap)
    result = mcp_server.analyze(str(test_repo), score_metrics="cyclomatic", compact=False)
    data = json.loads(result)
    assert "results" in data
    assert cap.rows is not None
    assert len(cap.rows) >= 2


def test_analyze_publishes_before_limit(monkeypatch, test_repo):
    monkeypatch.setattr(
        "hotspottriage.smell.compute_smells",
        lambda *args, **kwargs: [],
    )

    captured: dict[str, object] = {}

    class _Capturing:
        def publish_latest_block_metrics(self, rows, **kwargs):
            captured["rows"] = rows

    monkeypatch.setattr(mcp_server, "_dashboard_server_instance", _Capturing())
    out = mcp_server.analyze(str(test_repo), score_metrics="cyclomatic", limit=1, compact=False)
    data = json.loads(out)
    assert "results" in data
    rows = captured.get("rows")
    assert rows is not None
    assert isinstance(rows, list)
    assert len(rows) >= 2
    assert len(data["results"]) <= len(rows)


def test_analyze_empty_target_uses_default_target(monkeypatch, test_repo):
    monkeypatch.setattr(mcp_server, "_mcp_default_target", str(test_repo))
    monkeypatch.setattr(
        "hotspottriage.smell.compute_smells",
        lambda *args, **kwargs: [],
    )
    result = mcp_server.analyze("")
    data = json.loads(result)
    assert "results" in data and "cache" in data


def test_analyze_empty_without_default_target_errors(monkeypatch):
    monkeypatch.setattr(mcp_server, "_mcp_default_target", None)
    result = mcp_server.analyze("")
    data = json.loads(result)
    assert "error" in data
    assert "default-target" in data["error"].lower()


@pytest.mark.anyio
async def test_mcp_lifespan_dashboard_failure_is_non_fatal(monkeypatch):
    class _Boom:
        def __init__(self, **_: object) -> None:
            raise OSError("no free ports")

    monkeypatch.setattr(mcp_server, "DashboardServer", _Boom)
    async with mcp_server._mcp_lifespan(None):
        assert True


def test_analyze_filtered_dashboard_publish_excludes_other_cached_files(
    monkeypatch, test_repo
):
    """Scoped runs keep prior cache rows; dashboard publish must not restore them."""
    monkeypatch.setattr(
        "hotspottriage.smell.compute_smells",
        lambda *args, **kwargs: [],
    )

    publishes: list[list] = []

    class _Capturing:
        def publish_latest_block_metrics(self, rows, **kwargs):
            publishes.append(list(rows))

    monkeypatch.setattr(mcp_server, "_dashboard_server_instance", _Capturing())

    mcp_server.analyze(str(test_repo), score_metrics="cyclomatic", compact=False, similarity=False)
    mcp_server.analyze(
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


@pytest.fixture
def rev_pair_repo(tmp_path: Path) -> Path:
    """Two commits on ``a.py``: first only ``only()``, second adds ``second()``."""
    repo = tmp_path / "revpair"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "t@e.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "t"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "a.py").write_text("def only():\n    return 1\n")
    subprocess.run(["git", "add", "a.py"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "c1"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "a.py").write_text(
        "def only():\n    return 1\n\ndef second():\n    return 2\n"
    )
    subprocess.run(["git", "add", "a.py"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "c2"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return repo


def test_analyze_records_head_sha(test_repo: Path) -> None:
    result = mcp_server.analyze(str(test_repo), similarity=False, compact=True)
    data = json.loads(result)
    assert "error" not in data
    assert "head_sha" in data
    assert len(data["head_sha"]) == 40


def test_analyze_metadata_shape_and_git(test_repo: Path) -> None:
    result = mcp_server.analyze(str(test_repo), similarity=False, compact=True)
    data = json.loads(result)
    assert "error" not in data
    meta = data["metadata"]
    want_short = subprocess.check_output(
        ["git", "-C", str(test_repo), "rev-parse", "--short", "HEAD"],
        text=True,
    ).strip()
    assert meta["git_head"] == want_short
    assert isinstance(meta["git_branch"], str) and meta["git_branch"]
    assert meta["target"] == str(test_repo.resolve())
    assert isinstance(meta["filter_applied"], list)
    assert "**/*.py" in meta["filter_applied"]
    assert meta["row_count"] >= 1
    assert meta["truncated"] is False
    assert meta["config_fingerprint"].startswith("sha256:")
    assert len(meta["config_fingerprint"]) == len("sha256:") + 64
    assert meta["analyzed_at"].endswith("Z")


def test_analyze_metadata_truncated_when_limit_excludes_rows(test_repo: Path) -> None:
    result = mcp_server.analyze(
        str(test_repo), limit=1, similarity=False, compact=True
    )
    data = json.loads(result)
    meta = data["metadata"]
    assert meta["truncated"] is True
    assert meta["row_count"] > 1


def test_analyze_metadata_config_fingerprint_stable(test_repo: Path) -> None:
    a = json.loads(
        mcp_server.analyze(
            str(test_repo), similarity=False, compact=True, limit=5
        )
    )["metadata"]["config_fingerprint"]
    b = json.loads(
        mcp_server.analyze(
            str(test_repo), similarity=False, compact=True, limit=5
        )
    )["metadata"]["config_fingerprint"]
    assert a == b


def test_analyze_metadata_literal_or_filter_no_default_glob(test_repo: Path) -> None:
    result = mcp_server.analyze(
        str(test_repo),
        filter="example.py,helper.py",
        similarity=False,
        compact=True,
    )
    meta = json.loads(result)["metadata"]
    assert set(meta["filter_applied"]) == {"example.py", "helper.py"}


def test_analyze_before_sha_includes_deltas(rev_pair_repo: Path) -> None:
    lines = subprocess.check_output(
        ["git", "-C", str(rev_pair_repo), "rev-list", "--max-count=2", "--reverse", "HEAD"],
        text=True,
    ).splitlines()
    sha_old, sha_new = lines[0], lines[1]
    subprocess.run(
        ["git", "-C", str(rev_pair_repo), "checkout", sha_old],
        check=True,
        capture_output=True,
    )
    r1 = mcp_server.analyze(
        str(rev_pair_repo), filter="a.py", similarity=False, compact=False
    )
    d1 = json.loads(r1)
    assert "error" not in d1
    assert d1["head_sha"] == sha_old
    subprocess.run(
        ["git", "-C", str(rev_pair_repo), "checkout", sha_new],
        check=True,
        capture_output=True,
    )
    r2 = mcp_server.analyze(
        str(rev_pair_repo),
        before_sha=sha_old,
        filter="a.py",
        similarity=False,
        compact=False,
    )
    d2 = json.loads(r2)
    assert "error" not in d2
    assert d2["head_sha"] == sha_new
    assert "deltas" in d2
    assert d2["deltas"]["summary"]["blocks_added"] >= 1
    added = [b for b in d2["deltas"]["by_block"] if b["status"] == "added"]
    assert any("second" in b["path"] for b in added)
    symbols = {
        row["path"].split("::", 1)[1] for row in d2["results"] if "::" in row["path"]
    }
    assert "second" in symbols


def test_analyze_before_and_after_cache_only(rev_pair_repo: Path) -> None:
    lines = subprocess.check_output(
        ["git", "-C", str(rev_pair_repo), "rev-list", "--max-count=2", "--reverse", "HEAD"],
        text=True,
    ).splitlines()
    sha_old, sha_new = lines[0], lines[1]
    subprocess.run(
        ["git", "-C", str(rev_pair_repo), "checkout", sha_old],
        check=True,
        capture_output=True,
    )
    mcp_server.analyze(str(rev_pair_repo), filter="a.py", similarity=False, compact=False)
    subprocess.run(
        ["git", "-C", str(rev_pair_repo), "checkout", sha_new],
        check=True,
        capture_output=True,
    )
    mcp_server.analyze(str(rev_pair_repo), filter="a.py", similarity=False, compact=False)
    r3 = mcp_server.analyze(
        str(rev_pair_repo),
        before_sha=sha_old,
        after_sha=sha_new,
        filter="a.py",
        similarity=False,
        compact=False,
    )
    d3 = json.loads(r3)
    assert "error" not in d3
    assert "deltas" in d3
    assert d3["head_sha"] == sha_new
    want_short = subprocess.check_output(
        ["git", "-C", str(rev_pair_repo), "rev-parse", "--short", sha_new],
        text=True,
    ).strip()
    assert d3["metadata"]["git_branch"] == "snapshot"
    assert d3["metadata"]["git_head"] == want_short


def test_analyze_after_sha_requires_before(rev_pair_repo: Path) -> None:
    out = mcp_server._run_analyze_cached(
        str(rev_pair_repo),
        after_sha="HEAD",
        similarity=False,
    )
    assert "error" in json.loads(out)


def test_analyze_before_sha_missing_snapshot(rev_pair_repo: Path) -> None:
    root = subprocess.check_output(
        ["git", "-C", str(rev_pair_repo), "rev-list", "--max-parents=0", "HEAD"],
        text=True,
    ).strip()
    out = mcp_server._run_analyze_cached(
        str(rev_pair_repo),
        before_sha=root,
        similarity=False,
        filter="a.py",
    )
    data = json.loads(out)
    assert "error" in data
    assert "no cached snapshot" in data["error"].lower()


def test_analyze_before_after_rejects_remote_url() -> None:
    out = mcp_server._run_analyze_cached(
        "https://example.com/nonexistent.git",
        before_sha="0" * 40,
        after_sha="1" * 40,
        similarity=False,
    )
    data = json.loads(out)
    assert "error" in data
    assert "local" in data["error"].lower() or "remote" in data["error"].lower()
