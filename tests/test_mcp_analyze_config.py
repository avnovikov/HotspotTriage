"""Tests for :mod:`hotspottriage.mcp.analyze_config`."""

from pathlib import Path

from hotspottriage import config as ht_config
from hotspottriage.mcp.analyze_config import (
    build_analyze_config,
    effective_similarity_enabled_for_mcp_analyze,
)


def test_effective_similarity_matches_mcp_semantics() -> None:
    fn = effective_similarity_enabled_for_mcp_analyze
    assert fn(True, "a.py") is True
    assert fn(False, None) is False
    assert fn(None, None) is True
    assert fn(None, "") is True
    assert fn(None, "x.py") is False


def test_build_analyze_config_remote_url_starts_from_defaults() -> None:
    cfg = build_analyze_config("https://github.com/x/y.git", path_filter="a.py")
    assert cfg["filter"] == ["a.py"]
    assert cfg is not ht_config.DEFAULTS


def test_build_analyze_config_local_repo_layers(tiny_git_repo_with_example: Path) -> None:
    cfg = build_analyze_config(str(tiny_git_repo_with_example))
    want = ht_config.load_analyze_config_for_local_repo(tiny_git_repo_with_example)
    assert cfg["metric_normalization"] == want["metric_normalization"]
    assert cfg["score_aggregation"] == want["score_aggregation"]
