"""Tests for the layered YAML configuration system.

Covers each layer of the resolution order — defaults, global, project,
project.local, --config, and CLI flags — plus validation, merge semantics,
and the `init` template scaffolder.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pytest

from hotspottriage import config as _config


# --- _deep_merge ------------------------------------------------------------


def test_deep_merge_overlays_scalars():
    base = {"a": 1, "b": 2}
    out = _config._deep_merge(base, {"b": 99})
    assert out == {"a": 1, "b": 99}
    assert base == {"a": 1, "b": 2}


def test_deep_merge_replaces_lists_wholesale():
    base = {"filter": ["x", "y"]}
    out = _config._deep_merge(base, {"filter": ["only"]})
    assert out == {"filter": ["only"]}


def test_deep_merge_recurses_into_nested_dicts():
    base = {"nested": {"a": 1, "b": 2}}
    out = _config._deep_merge(base, {"nested": {"b": 20, "c": 30}})
    assert out == {"nested": {"a": 1, "b": 20, "c": 30}}


# --- merge_dashboard_config_patch -------------------------------------------


def test_merge_dashboard_config_patch_noop_without_file(tmp_path: Path):
    repo = tmp_path / "r"
    repo.mkdir()
    base = {"format": "json", "filter": ["x"]}
    out = _config.merge_dashboard_config_patch(repo, base)
    assert out == base
    assert out is not base


def test_merge_dashboard_config_patch_merges_score_aggregation(tmp_path: Path):
    from copy import deepcopy

    repo = tmp_path / "r"
    repo.mkdir()
    cfg_dir = repo / ".hotspottriage"
    cfg_dir.mkdir()
    (cfg_dir / "dashboard_config_patch.yml").write_text(
        """
score_aggregation:
  final_weights:
    complexity_burden: 0.50
    churn_burden: 0.20
    maintainability_burden: 0.15
    smell_burden: 0.10
    similarity_burden: 0.05
""".strip()
        + "\n"
    )
    merged = _config.merge_dashboard_config_patch(repo, deepcopy(_config.DEFAULTS))
    _config.validate(merged)
    assert merged["score_aggregation"]["final_weights"]["complexity_burden"] == 0.5


def test_merge_dashboard_config_patch_rejects_unknown_top_level(tmp_path: Path):
    from copy import deepcopy

    repo = tmp_path / "r2"
    repo.mkdir()
    cfg_dir = repo / ".hotspottriage"
    cfg_dir.mkdir()
    (cfg_dir / "dashboard_config_patch.yml").write_text("not_a_real_key: true\n")
    with pytest.raises(AssertionError):
        _config.merge_dashboard_config_patch(repo, deepcopy(_config.DEFAULTS))


def test_load_analyze_config_for_local_repo_merges_project_and_patch(tmp_path: Path):
    cfg_dir = tmp_path / ".hotspottriage"
    cfg_dir.mkdir()
    (cfg_dir / "project.yml").write_text("smell_weight: 0.5\n")
    (cfg_dir / "dashboard_config_patch.yml").write_text(
        """
score_aggregation:
  final_weights:
    complexity_burden: 0.11
    churn_burden: 0.22
    maintainability_burden: 0.22
    smell_burden: 0.22
    similarity_burden: 0.23
""".strip()
        + "\n"
    )
    merged = _config.load_analyze_config_for_local_repo(tmp_path)
    _config.validate(merged)
    assert merged["smell_weight"] == 0.5
    assert merged["score_aggregation"]["final_weights"]["complexity_burden"] == 0.11


# --- load_config ------------------------------------------------------------


def _isolate_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Redirect both HOME and the module-level GLOBAL_CONFIG_* paths so a
    real ~/.hotspottriage/ on the developer's machine cannot pollute tests."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setattr(_config, "GLOBAL_CONFIG_DIR", fake_home / ".hotspottriage")
    monkeypatch.setattr(
        _config, "GLOBAL_CONFIG_FILE", fake_home / ".hotspottriage" / "config.yml"
    )
    return fake_home


def test_load_config_with_no_files_returns_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    _isolate_home(monkeypatch, tmp_path)
    cfg = _config.load_config(target_path=None)
    assert cfg == _config.DEFAULTS
    assert cfg is not _config.DEFAULTS  # deep copy guarantees no mutation


def test_load_config_global_layer_overrides_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    _isolate_home(monkeypatch, tmp_path)
    _config.GLOBAL_CONFIG_DIR.mkdir(parents=True)
    _config.GLOBAL_CONFIG_FILE.write_text("format: csv\nlimit: 10\n")
    cfg = _config.load_config(target_path=None)
    assert cfg["format"] == "csv"
    assert cfg["limit"] == 10
    # Untouched keys still inherit the built-in defaults.
    assert cfg["sort"] == _config.DEFAULTS["sort"]


def test_load_config_project_overrides_global(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    _isolate_home(monkeypatch, tmp_path)
    _config.GLOBAL_CONFIG_DIR.mkdir(parents=True)
    _config.GLOBAL_CONFIG_FILE.write_text("format: csv\nlimit: 10\n")

    repo = tmp_path / "repo"
    cfg_dir = repo / ".hotspottriage"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "project.yml").write_text("format: json\n")

    cfg = _config.load_config(target_path=repo)
    assert cfg["format"] == "json"  # project beats global
    assert cfg["limit"] == 10  # global still applies for keys project did not set


def test_load_config_local_overrides_project(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    _isolate_home(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    cfg_dir = repo / ".hotspottriage"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "project.yml").write_text("format: csv\n")
    (cfg_dir / "project.local.yml").write_text("format: table\n")
    cfg = _config.load_config(target_path=repo)
    assert cfg["format"] == "table"


def test_load_config_explicit_overrides_everything(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    _isolate_home(monkeypatch, tmp_path)
    _config.GLOBAL_CONFIG_DIR.mkdir(parents=True)
    _config.GLOBAL_CONFIG_FILE.write_text("format: csv\n")
    repo = tmp_path / "repo"
    cfg_dir = repo / ".hotspottriage"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "project.yml").write_text("format: json\n")

    explicit = tmp_path / "extra.yml"
    explicit.write_text("format: table\n")

    cfg = _config.load_config(target_path=repo, explicit=explicit)
    assert cfg["format"] == "table"


def test_load_config_no_global_flag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    _isolate_home(monkeypatch, tmp_path)
    _config.GLOBAL_CONFIG_DIR.mkdir(parents=True)
    _config.GLOBAL_CONFIG_FILE.write_text("format: csv\n")
    cfg = _config.load_config(target_path=None, use_global=False)
    assert cfg["format"] == _config.DEFAULTS["format"]


def test_load_config_no_project_flag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    _isolate_home(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    cfg_dir = repo / ".hotspottriage"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "project.yml").write_text("format: csv\n")
    cfg = _config.load_config(target_path=repo, use_project=False)
    assert cfg["format"] == _config.DEFAULTS["format"]


def test_load_config_explicit_path_must_exist(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    _isolate_home(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="--config path does not exist"):
        _config.load_config(target_path=None, explicit=tmp_path / "missing.yml")


def test_load_config_rejects_unknown_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    _isolate_home(monkeypatch, tmp_path)
    _config.GLOBAL_CONFIG_DIR.mkdir(parents=True)
    _config.GLOBAL_CONFIG_FILE.write_text("typo_key: 42\n")
    with pytest.raises(AssertionError, match="unknown config key"):
        _config.load_config(target_path=None)


def test_load_config_rejects_non_mapping(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    _isolate_home(monkeypatch, tmp_path)
    _config.GLOBAL_CONFIG_DIR.mkdir(parents=True)
    _config.GLOBAL_CONFIG_FILE.write_text("- a\n- b\n")
    with pytest.raises(ValueError, match="must contain a YAML mapping"):
        _config.load_config(target_path=None)


def test_load_config_rejects_invalid_yaml(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    _isolate_home(monkeypatch, tmp_path)
    _config.GLOBAL_CONFIG_DIR.mkdir(parents=True)
    _config.GLOBAL_CONFIG_FILE.write_text("a: [unterminated\n")
    with pytest.raises(ValueError, match="invalid YAML"):
        _config.load_config(target_path=None)


def test_load_config_empty_file_is_noop(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    _isolate_home(monkeypatch, tmp_path)
    _config.GLOBAL_CONFIG_DIR.mkdir(parents=True)
    _config.GLOBAL_CONFIG_FILE.write_text("")
    cfg = _config.load_config(target_path=None)
    assert cfg == _config.DEFAULTS


# --- apply_cli_overrides ----------------------------------------------------


def _ns(**kwargs) -> argparse.Namespace:
    """Build a Namespace whose default values match the CLI parser sentinels:
    every flag is None (i.e. "not passed") unless overridden in kwargs."""
    base = {
        "filter": None,
        "no_default_filter": None,
        "score": None,
        "format": None,
        "limit": None,
        "since": None,
        "until": None,
        "sort": None,
        "directories": None,
        "granularity": None,
        "ignore_dir": None,
        "no_respect_gitignore": None,
    }
    base.update(kwargs)
    return argparse.Namespace(**base)


def test_apply_cli_overrides_skips_none_sentinels():
    cfg = dict(_config.DEFAULTS)
    out = _config.apply_cli_overrides(cfg, _ns())
    assert out == cfg


def test_apply_cli_overrides_csv_score_metrics():
    cfg = dict(_config.DEFAULTS)
    out = _config.apply_cli_overrides(cfg, _ns(score="churn,cyclomatic"))
    assert out["score_metrics"] == ["churn", "cyclomatic"]


def test_apply_cli_overrides_csv_filter():
    cfg = dict(_config.DEFAULTS)
    out = _config.apply_cli_overrides(cfg, _ns(filter="src/**,!tests/**"))
    assert out["filter"] == ["src/**", "!tests/**"]


def test_apply_cli_overrides_empty_filter_does_not_override():
    cfg = {**_config.DEFAULTS, "filter": ["already_set"]}
    out = _config.apply_cli_overrides(cfg, _ns(filter=""))
    # An empty --filter string should NOT wipe out a config-file setting.
    assert out["filter"] == ["already_set"]


def test_apply_cli_overrides_truthy_store_true_flag():
    cfg = dict(_config.DEFAULTS)
    out = _config.apply_cli_overrides(cfg, _ns(directories=True))
    assert out["directories"] is True


def test_apply_cli_overrides_passthrough_scalars():
    cfg = dict(_config.DEFAULTS)
    out = _config.apply_cli_overrides(
        cfg,
        _ns(format="json", limit=5, sort="file", since="1 week", granularity="block"),
    )
    assert out["format"] == "json"
    assert out["limit"] == 5
    assert out["sort"] == "file"
    assert out["since"] == "1 week"
    assert out["granularity"] == "block"


# --- validate ---------------------------------------------------------------


def test_validate_accepts_defaults():
    _config.validate(dict(_config.DEFAULTS))


def test_validate_rejects_bad_dashboard_host():
    cfg = {**_config.DEFAULTS, "dashboard": {**_config.DEFAULTS["dashboard"], "host": ""}}
    with pytest.raises(ValueError, match="dashboard.host"):
        _config.validate(cfg)


def test_validate_rejects_dashboard_default_target_non_string():
    cfg = {
        **_config.DEFAULTS,
        "dashboard": {**_config.DEFAULTS["dashboard"], "default_target": 123},
    }
    with pytest.raises(ValueError, match="dashboard.default_target"):
        _config.validate(cfg)


def test_to_dashboard_snapshot_shape():
    snap = _config.to_dashboard_snapshot(dict(_config.DEFAULTS), project_path="/tmp/r")
    assert snap["version"]
    assert snap["project"]["path"] == "/tmp/r"
    assert "score_metrics" in snap and isinstance(snap["score_metrics"], list)
    assert "dashboard" in snap and snap["dashboard"]["base_port"] == 9123
    assert "proposed_models" in snap and isinstance(snap["proposed_models"], dict)


def test_apply_mcp_dashboard_cli_overrides():
    base = dict(_config.DEFAULTS)
    out = _config.apply_mcp_dashboard_cli_overrides(
        base,
        no_dashboard=True,
        dashboard_port=9200,
        dashboard_host="0.0.0.0",
        open_browser=True,
    )
    assert out["dashboard"]["enabled"] is False
    assert out["dashboard"]["base_port"] == 9200
    assert out["dashboard"]["host"] == "0.0.0.0"
    assert out["dashboard"]["open_on_start"] is True
    _config.validate(out)


def test_validate_rejects_unknown_score_metric():
    cfg = {**_config.DEFAULTS, "score_metrics": ["bogus"]}
    with pytest.raises(ValueError, match="unknown score metric"):
        _config.validate(cfg)


def test_validate_rejects_empty_score_metrics():
    cfg = {**_config.DEFAULTS, "score_metrics": []}
    with pytest.raises(ValueError, match="non-empty list"):
        _config.validate(cfg)


def test_validate_rejects_unknown_format():
    cfg = {**_config.DEFAULTS, "format": "yaml"}
    with pytest.raises(ValueError, match="unknown format"):
        _config.validate(cfg)


def test_validate_rejects_unknown_sort():
    cfg = {**_config.DEFAULTS, "sort": "bogus"}
    with pytest.raises(ValueError, match="unknown sort key"):
        _config.validate(cfg)


def test_validate_allows_similarity_enabled_with_file_granularity():
    """similarity_enabled applies only when building block stats; file mode ignores it."""
    cfg = {**_config.DEFAULTS, "similarity_enabled": True, "granularity": "file"}
    _config.validate(cfg)


def test_validate_rejects_smell_rule_weight_out_of_range():
    cfg = {
        **_config.DEFAULTS,
        "smell_rule_weights": {**_config.DEFAULTS["smell_rule_weights"], "x": 1.5},
    }
    with pytest.raises(ValueError, match="smell_rule_weights"):
        _config.validate(cfg)


def test_validate_rejects_similarity_score_metric_without_block():
    cfg = {
        **_config.DEFAULTS,
        "granularity": "file",
        "score_metrics": ["cyclomatic", "similarity_score"],
    }
    with pytest.raises(ValueError, match="similarity_score"):
        _config.validate(cfg)


def test_validate_rejects_unknown_granularity():
    cfg = {**_config.DEFAULTS, "granularity": "module"}
    with pytest.raises(ValueError, match="unknown granularity"):
        _config.validate(cfg)


def test_validate_rejects_unknown_log_level():
    cfg = {**_config.DEFAULTS, "log_level": "verbose"}
    with pytest.raises(ValueError, match="unknown log_level"):
        _config.validate(cfg)


def test_validate_rejects_negative_limit():
    cfg = {**_config.DEFAULTS, "limit": -1}
    with pytest.raises(ValueError, match="limit must be"):
        _config.validate(cfg)


def test_validate_rejects_zero_workers():
    cfg = {**_config.DEFAULTS, "block_workers": 0}
    with pytest.raises(ValueError, match="block_workers must be"):
        _config.validate(cfg)


def test_validate_rejects_invalid_smell_threshold():
    cfg = {**_config.DEFAULTS, "smell_max_args": 0}
    with pytest.raises(ValueError, match="smell_max_args must be a positive int"):
        _config.validate(cfg)


def test_validate_rejects_invalid_comment_ratio_threshold():
    cfg = {**_config.DEFAULTS, "smell_max_comment_ratio": 0}
    with pytest.raises(ValueError, match="smell_max_comment_ratio must be a positive number"):
        _config.validate(cfg)


def test_validate_rejects_invalid_middle_man_sloc_threshold():
    cfg = {**_config.DEFAULTS, "smell_middle_man_max_avg_method_sloc": 0}
    with pytest.raises(
        ValueError, match="smell_middle_man_max_avg_method_sloc must be a positive number"
    ):
        _config.validate(cfg)


def test_validate_rejects_negative_smell_weight():
    cfg = {**_config.DEFAULTS, "smell_weight": -0.1}
    with pytest.raises(ValueError, match="smell_weight must be a non-negative number"):
        _config.validate(cfg)


def test_validate_rejects_block_directories_combo():
    cfg = {**_config.DEFAULTS, "granularity": "block", "directories": True}
    with pytest.raises(ValueError, match="cannot be combined"):
        _config.validate(cfg)


def test_validate_rejects_non_bool_respect_gitignore():
    cfg = {**_config.DEFAULTS, "respect_gitignore": "yes"}
    with pytest.raises(ValueError, match="respect_gitignore must be a boolean"):
        _config.validate(cfg)


def test_validate_rejects_bad_ignore_directories_type():
    cfg = {**_config.DEFAULTS, "ignore_directories": "vendor"}
    with pytest.raises(ValueError, match="ignore_directories must be a list"):
        _config.validate(cfg)


def test_validate_rejects_ignore_directories_with_dotdot():
    cfg = {**_config.DEFAULTS, "ignore_directories": ["../secret"]}
    with pytest.raises(ValueError, match="ignore_directories entry"):
        _config.validate(cfg)


def test_apply_cli_merges_ignore_dir_flags():
    cfg = {**_config.DEFAULTS, "ignore_directories": ["a"]}
    out = _config.apply_cli_overrides(
        cfg,
        _ns(ignore_dir=["b", "c"]),
    )
    assert out["ignore_directories"] == ["a", "b", "c"]


def test_apply_cli_no_respect_gitignore():
    cfg = {**_config.DEFAULTS, "respect_gitignore": True}
    out = _config.apply_cli_overrides(cfg, _ns(no_respect_gitignore=True))
    assert out["respect_gitignore"] is False


# --- init_config ------------------------------------------------------------


def test_init_global_writes_template(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    _isolate_home(monkeypatch, tmp_path)
    written = _config.init_config("global")
    assert written == _config.GLOBAL_CONFIG_FILE
    text = _config.GLOBAL_CONFIG_FILE.read_text()
    assert "score_metrics:" in text
    assert "format: table" in text


def test_init_global_refuses_overwrite(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    _isolate_home(monkeypatch, tmp_path)
    _config.init_config("global")
    with pytest.raises(FileExistsError):
        _config.init_config("global")


def test_init_project_writes_template_and_gitignore(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    _isolate_home(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    written = _config.init_config("project", repo)
    cfg_dir = repo / ".hotspottriage"
    assert written == cfg_dir / "project.yml"
    assert (cfg_dir / "project.yml").is_file()
    assert (cfg_dir / "project.local.yml").is_file()
    assert (cfg_dir / ".gitignore").read_text().strip() == "project.local.yml"


def test_init_project_refuses_overwrite_of_project_yml(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    _isolate_home(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    _config.init_config("project", repo)
    with pytest.raises(FileExistsError):
        _config.init_config("project", repo)


def test_init_project_requires_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    _isolate_home(monkeypatch, tmp_path)
    not_a_dir = tmp_path / "missing"
    with pytest.raises(NotADirectoryError):
        _config.init_config("project", not_a_dir)


def test_init_unknown_scope():
    with pytest.raises(ValueError, match="unknown init scope"):
        _config.init_config("server", Path("/tmp"))


# --- end-to-end through the CLI --------------------------------------------


def test_cli_init_global_subcommand(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """The `init --global` subcommand wires up correctly through main()."""
    _isolate_home(monkeypatch, tmp_path)
    fake_home = tmp_path / "home"
    r = subprocess.run(
        [sys.executable, "-m", "hotspottriage", "init", "--global"],
        capture_output=True,
        text=True,
        env={
            **{k: v for k, v in __import__("os").environ.items()},
            "HOME": str(fake_home),
        },
    )
    assert r.returncode == 0, r.stderr
    assert (fake_home / ".hotspottriage" / "config.yml").is_file()


def test_cli_init_project_subcommand(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    r = subprocess.run(
        [
            sys.executable, "-m", "hotspottriage",
            "init", "--project", str(repo),
        ],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    assert (repo / ".hotspottriage" / "project.yml").is_file()
    assert (repo / ".hotspottriage" / "project.local.yml").is_file()
