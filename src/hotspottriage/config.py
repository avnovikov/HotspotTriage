"""Layered YAML configuration for HotspotTriage.

Resolution order (last wins):

    code DEFAULTS
      -> ~/.hotspottriage/config.yml          (global, per user)
      -> <repo>/.hotspottriage/project.yml    (per project, versioned)
      -> <repo>/.hotspottriage/project.local.yml (per machine, gitignored)
      -> --config <PATH>                      (explicit override file)
      -> CLI flags                            (only when explicitly passed)

A layer only needs to specify the keys it wants to override; missing keys fall
through to the next lower layer.

This module is the single source of truth for default values; CLI argparse
defaults are intentionally `None` sentinels so we can distinguish "user passed
this flag" from "user did not pass it".
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from hotspottriage import filtering as _filtering
from hotspottriage import output as _output
from hotspottriage import stats as _stats

GLOBAL_CONFIG_DIR = Path.home() / ".hotspottriage"
GLOBAL_CONFIG_FILE = GLOBAL_CONFIG_DIR / "config.yml"

PROJECT_CONFIG_DIRNAME = ".hotspottriage"
PROJECT_CONFIG_FILENAME = "project.yml"
PROJECT_LOCAL_CONFIG_FILENAME = "project.local.yml"
PROJECT_GITIGNORE_FILENAME = ".gitignore"

# Single source of truth for every configurable setting.
DEFAULTS: dict[str, Any] = {
    "filter": [],
    "no_default_filter": False,
    "default_filter": "**/*.py",
    "score_metrics": ["decayed_churn_per_sloc", "cyclomatic"],
    "format": "table",
    "limit": None,
    "sort": "score",
    "granularity": "file",
    "since": None,
    "until": None,
    "directories": False,
    "ignore_directories": [],
    "respect_gitignore": True,
    "block_workers": None,
    "cache_dir": None,
    "log_level": "warning",
    "decay_half_life": 2592000,  # 30 days in seconds
    "smell_weight": 0.0,
    "smell_max_statements": 50,
    "smell_max_attributes": 10,
    "smell_max_public_methods": 20,
    "smell_max_args": 5,
    "smell_max_branches": 12,
    "smell_min_public_methods": 2,
    "smell_max_comment_ratio": 0.5,
    "smell_max_comment_block_lines": 15,
    "smell_data_class_min_attributes": 8,
    "smell_middle_man_max_avg_method_sloc": 2.0,
    "smell_speculative_generality_min_hits": 1,
    # null = auto (TTY stderr), true/false = force on/off
    "progress": None,
    # DeepCSIM pairwise similarity for block runs (ignored for file granularity).
    "similarity_enabled": True,
    "similarity_threshold": 80.0,
    "similarity_band_high": 85.0,
    "similarity_band_medium": 70.0,
    "similarity_band_low": 50.0,
    "similarity_max_pairwise_blocks": 2500,
    "similarity_aggregate_row": True,
}

_VALID_LOG_LEVELS = ("debug", "info", "warning", "error")
_VALID_GRANULARITY = ("file", "block")


def _read_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file as a dict. Empty files return {}.

    Raises ValueError with an actionable message on parse errors or non-mapping
    top-levels — silent failures here would let a typo override real settings.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ValueError(f"cannot read config file {path}: {e}") from e
    if not text.strip():
        return {}
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ValueError(f"invalid YAML in {path}: {e}") from e
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(
            f"config file {path} must contain a YAML mapping at the top level; "
            f"got {type(data).__name__}"
        )
    return data


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Merge `overlay` into `base` recursively. Lists/scalars are replaced
    wholesale; only dicts merge key-by-key. The base dict is not mutated."""
    out = deepcopy(base)
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = deepcopy(v)
    return out


def _reject_unknown_keys(data: dict[str, Any], path: Path) -> None:
    unknown = sorted(set(data) - set(DEFAULTS))
    assert not unknown, (
        f"unknown config key(s) in {path}: {unknown} "
        f"(valid keys: {sorted(DEFAULTS)})"
    )


def discover_config_paths(
    target_path: Path | None,
    *,
    explicit: Path | None = None,
    use_global: bool = True,
    use_project: bool = True,
) -> list[Path]:
    """Return the ordered list of config files that exist for this run.

    Layered lowest-precedence first; callers feed them through `_deep_merge`
    in the same order so later layers override earlier ones.
    """
    paths: list[Path] = []
    if use_global and GLOBAL_CONFIG_FILE.is_file():
        paths.append(GLOBAL_CONFIG_FILE)
    if use_project and target_path is not None:
        project_dir = Path(target_path) / PROJECT_CONFIG_DIRNAME
        project_yml = project_dir / PROJECT_CONFIG_FILENAME
        local_yml = project_dir / PROJECT_LOCAL_CONFIG_FILENAME
        if project_yml.is_file():
            paths.append(project_yml)
        if local_yml.is_file():
            paths.append(local_yml)
    if explicit is not None:
        if not explicit.is_file():
            raise ValueError(f"--config path does not exist: {explicit}")
        paths.append(explicit)
    return paths


def load_config(
    target_path: Path | None,
    *,
    explicit: Path | None = None,
    use_global: bool = True,
    use_project: bool = True,
) -> dict[str, Any]:
    """Load and merge every applicable config layer.

    `target_path` is the local repo directory whose `.hotspottriage/` folder
    we should consult — None means "no project layer" (e.g. before the target
    has been resolved, or for `--no-config` runs).
    """
    merged = deepcopy(DEFAULTS)
    for path in discover_config_paths(
        target_path,
        explicit=explicit,
        use_global=use_global,
        use_project=use_project,
    ):
        layer = _read_yaml(path)
        _reject_unknown_keys(layer, path)
        merged = _deep_merge(merged, layer)
    return merged


# CLI argument name -> config key. Only flags that map to a config setting
# go here; one-shot flags like --config / --no-config are handled in cli.py.
_CLI_TO_CONFIG: dict[str, str] = {
    "filter": "filter",
    "no_default_filter": "no_default_filter",
    "score": "score_metrics",
    "format": "format",
    "limit": "limit",
    "since": "since",
    "until": "until",
    "sort": "sort",
    "directories": "directories",
    "granularity": "granularity",
}


def _parse_csv(raw: str | list[str]) -> list[str]:
    """Accept either a CSV string (from CLI) or a YAML list and normalise to a
    clean list of non-empty trimmed strings."""
    if isinstance(raw, list):
        return [str(s).strip() for s in raw if str(s).strip()]
    return [s for s in (p.strip() for p in str(raw).split(",")) if s]


def apply_cli_overrides(
    config: dict[str, Any], args: argparse.Namespace
) -> dict[str, Any]:
    """Layer explicit CLI args on top of the merged config.

    A CLI arg "explicitly passed" means: not None for optional-valued flags;
    truthy for store_true flags. Booleans are tricky because argparse can't
    natively distinguish "user passed --no-default-filter" from "user did not";
    we treat True as override, False as "leave config alone". This means a
    config setting `no_default_filter: true` cannot be re-disabled on the CLI,
    which matches every other "store_true" tool's semantics.
    """
    out = deepcopy(config)
    for cli_key, cfg_key in _CLI_TO_CONFIG.items():
        if not hasattr(args, cli_key):
            continue
        val = getattr(args, cli_key)
        if val is None:
            continue
        if isinstance(val, bool):
            if val:
                out[cfg_key] = True
            continue
        if cfg_key == "score_metrics":
            out[cfg_key] = _parse_csv(val)
            continue
        if cfg_key == "filter":
            csv_val = _parse_csv(val)
            if csv_val:
                out[cfg_key] = csv_val
            continue
        out[cfg_key] = val

    # Flags handled outside the generic _CLI_TO_CONFIG loop.
    if getattr(args, "no_respect_gitignore", None):
        out["respect_gitignore"] = False

    extra_dirs = getattr(args, "ignore_dir", None)
    if extra_dirs:
        merged_dirs = list(out.get("ignore_directories") or [])
        merged_dirs.extend(extra_dirs)
        out["ignore_directories"] = merged_dirs

    return out


def validate(config: dict[str, Any]) -> None:
    """Validate a fully-merged config. Raises ValueError on the first problem.

    Defensive check: catches typos / bad values from any layer (file or CLI)
    before they reach the analysis pipeline, where the failure mode is harder
    to debug ("why is my output empty?").
    """
    score_metrics = config.get("score_metrics") or []
    if not isinstance(score_metrics, list) or not score_metrics:
        raise ValueError("score_metrics must be a non-empty list")
    bad = [m for m in score_metrics if m not in _stats.SCORE_METRICS]
    if bad:
        raise ValueError(
            f"unknown score metric(s): {bad} "
            f"(valid: {list(_stats.SCORE_METRICS)})"
        )

    fmt = config.get("format")
    if fmt not in _output.FORMATS:
        raise ValueError(
            f"unknown format: {fmt!r} (valid: {list(_output.FORMATS)})"
        )

    sort = config.get("sort")
    if sort not in _stats.SORT_KEYS:
        raise ValueError(
            f"unknown sort key: {sort!r} (valid: {list(_stats.SORT_KEYS)})"
        )

    granularity = config.get("granularity")
    if granularity not in _VALID_GRANULARITY:
        raise ValueError(
            f"unknown granularity: {granularity!r} "
            f"(valid: {list(_VALID_GRANULARITY)})"
        )

    log_level = config.get("log_level")
    if log_level not in _VALID_LOG_LEVELS:
        raise ValueError(
            f"unknown log_level: {log_level!r} "
            f"(valid: {list(_VALID_LOG_LEVELS)})"
        )

    limit = config.get("limit")
    if limit is not None and (not isinstance(limit, int) or limit < 0):
        raise ValueError(f"limit must be null or a non-negative int; got {limit!r}")

    workers = config.get("block_workers")
    if workers is not None and (not isinstance(workers, int) or workers < 1):
        raise ValueError(
            f"block_workers must be null or a positive int; got {workers!r}"
        )

    if config.get("granularity") == "block" and config.get("directories"):
        raise ValueError("`directories` cannot be combined with `granularity: block`")

    rg = config.get("respect_gitignore")
    if not isinstance(rg, bool):
        raise ValueError(
            f"respect_gitignore must be a boolean; got {type(rg).__name__}: {rg!r}"
        )

    ign = config.get("ignore_directories") or []
    if not isinstance(ign, list):
        raise ValueError(
            f"ignore_directories must be a list; got {type(ign).__name__}: {ign!r}"
        )
    for entry in ign:
        if not isinstance(entry, str):
            raise ValueError(
                f"ignore_directories entries must be strings; got {entry!r}"
            )
        _filtering.normalize_directory_prefix(entry)

    decay_hl = config.get("decay_half_life")
    if decay_hl is not None and (not isinstance(decay_hl, int) or decay_hl < 1):
        raise ValueError(
            f"decay_half_life must be null or a positive int (seconds); got {decay_hl!r}"
        )
    smell_weight = config.get("smell_weight")
    if not isinstance(smell_weight, (int, float)) or smell_weight < 0:
        raise ValueError(
            f"smell_weight must be a non-negative number; got {smell_weight!r}"
        )

    smell_keys = (
        "smell_max_statements",
        "smell_max_attributes",
        "smell_max_public_methods",
        "smell_max_args",
        "smell_max_branches",
        "smell_min_public_methods",
        "smell_max_comment_block_lines",
        "smell_data_class_min_attributes",
        "smell_speculative_generality_min_hits",
    )
    for key in smell_keys:
        value = config.get(key)
        if not isinstance(value, int) or value < 1:
            raise ValueError(f"{key} must be a positive int; got {value!r}")

    comment_ratio = config.get("smell_max_comment_ratio")
    if not isinstance(comment_ratio, (int, float)) or comment_ratio <= 0:
        raise ValueError(
            f"smell_max_comment_ratio must be a positive number; got {comment_ratio!r}"
        )

    middle_man_avg_sloc = config.get("smell_middle_man_max_avg_method_sloc")
    if not isinstance(middle_man_avg_sloc, (int, float)) or middle_man_avg_sloc <= 0:
        raise ValueError(
            "smell_middle_man_max_avg_method_sloc must be a positive number; "
            f"got {middle_man_avg_sloc!r}"
        )

    progress = config.get("progress")
    if progress is not None and not isinstance(progress, bool):
        raise ValueError(
            f"progress must be null or a boolean; got {type(progress).__name__}: {progress!r}"
        )

    if "similarity_score" in score_metrics and config.get("granularity") != "block":
        raise ValueError(
            "score_metrics cannot include similarity_score unless granularity is block"
        )

    sim_en = config.get("similarity_enabled")
    if not isinstance(sim_en, bool):
        raise ValueError(
            f"similarity_enabled must be a boolean; got {type(sim_en).__name__}: {sim_en!r}"
        )
    st = config.get("similarity_threshold")
    if not isinstance(st, (int, float)) or not (0 < st <= 100):
        raise ValueError(
            f"similarity_threshold must be between 0 and 100 (exclusive 0); got {st!r}"
        )
    for key in (
        "similarity_band_high",
        "similarity_band_medium",
        "similarity_band_low",
    ):
        v = config.get(key)
        if not isinstance(v, (int, float)) or not (0 < v <= 100):
            raise ValueError(f"{key} must be a number in (0, 100]; got {v!r}")
    bh = float(config["similarity_band_high"])
    bm = float(config["similarity_band_medium"])
    bl = float(config["similarity_band_low"])
    if not (bh >= bm >= bl):
        raise ValueError(
            "similarity_band_high >= similarity_band_medium >= similarity_band_low is required"
        )
    smb = config.get("similarity_max_pairwise_blocks")
    if not isinstance(smb, int) or smb < 2:
        raise ValueError(
            f"similarity_max_pairwise_blocks must be an int >= 2; got {smb!r}"
        )
    sar = config.get("similarity_aggregate_row")
    if not isinstance(sar, bool):
        raise ValueError(
            f"similarity_aggregate_row must be a boolean; got {type(sar).__name__}: {sar!r}"
        )


# --- Template generation (`init` subcommand) -----------------------------

_GLOBAL_TEMPLATE = """\
# HotspotTriage global configuration.
#
# Lives at ~/.hotspottriage/config.yml and applies to every run on this
# machine. Per-project files in <repo>/.hotspottriage/project.yml override
# these values; CLI flags override both.
#
# Every key is optional — delete or comment out the ones you do not want
# to override.

# Default filter patterns (gitignore syntax, AND semantics, '!' negates).
# Equivalent to --filter on the CLI.
filter: []

# Disable the built-in '**/*.py' filter so non-Python files are included.
no_default_filter: false

# Which metrics multiply into the `score` column.
# Valid: sloc, cyclomatic, halstead, maintainability, churn, churn_per_sloc, decayed_churn, decayed_churn_per_sloc
score_metrics:
  - decayed_churn_per_sloc
  - cyclomatic

# Output format: table | json | csv
format: table

# Max rows to print (null = unlimited).
limit: null

# Sort key: score | file
sort: score

# Granularity: file | block
granularity: file

# Date window for churn (anything `git log --since` accepts).
since: null
until: null

# Aggregate results by directory instead of individual files.
# Cannot be combined with `granularity: block`.
directories: false

# --- Advanced -----------------------------------------------------------

# Block-churn thread pool size (null = min(16, cpu_count*2)).
block_workers: null

# Cache directory (null = $XDG_CACHE_HOME or ~/.cache).
cache_dir: null

# Logging verbosity: debug | info | warning | error
log_level: warning

# Exponential decay half-life for churn, in seconds (default: 30 days).
# Recent changes weigh more heavily than old ones. Set to a larger value to
# reduce the impact of aging, or disable via `decay_half_life: null`.
decay_half_life: 2592000

# Weight applied when score_metrics includes smell_count.
# Score factor contribution: 1 + (smell_weight * smell_count)
# Keep 0.0 for neutral behavior (legacy-compatible scoring).
smell_weight: 0.0

# Show Rich progress on stderr during analysis. null = auto (TTY only).
progress: null

# DeepCSIM block similarity (block granularity only; no-op for file rows). Adds
# similarity_score, similarity_band, match_count per block and an optional aggregate row.
# similarity_enabled: true
# similarity_threshold: 80.0
# similarity_aggregate_row: true

# Drop any tracked path under these POSIX prefixes (after normalisation).
# Example: ['vendor', 'generated/proto']
ignore_directories: []

# Apply .gitignore, nested **/.gitignore, and .git/info/exclude to tracked paths.
respect_gitignore: true
"""

_PROJECT_TEMPLATE = """\
# HotspotTriage per-project configuration.
#
# Lives at <repo>/.hotspottriage/project.yml. Versioned; commit this file
# so every contributor gets the same defaults. Use project.local.yml for
# machine-specific overrides (gitignored).
#
# Every key is optional — only specify settings you want to override
# from the global config / built-in defaults.

# Default filter patterns specific to this project, e.g. ['src/**'].
filter: []

# Override the score recipe for this project, e.g. emphasize maintainability:
# score_metrics:
#   - decayed_churn_per_sloc
#   - maintainability
score_metrics:
  - decayed_churn_per_sloc
  - cyclomatic

# Default output format for this project.
format: table

# Default sort: score | file
sort: score

# Default granularity: file | block
granularity: file

# Directory prefixes to exclude from analysis (POSIX paths under the repo).
ignore_directories: []

# Apply gitignore rules to tracked files (set false to analyse everything).
respect_gitignore: true
"""

_PROJECT_LOCAL_TEMPLATE = """\
# HotspotTriage per-project, per-machine overrides.
#
# This file is gitignored. Use it for personal preferences that should
# not be committed (e.g. different output format, custom date windows).
# Same keys as project.yml; anything you set here overrides project.yml.
"""

_PROJECT_GITIGNORE = """\
project.local.yml
"""


def init_config(scope: str, target: Path | None = None) -> Path:
    """Scaffold a config template. Returns the primary file written.

    `scope` is 'global' or 'project'. For project scope, `target` must be
    the repo root.
    """
    if scope == "global":
        GLOBAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if GLOBAL_CONFIG_FILE.exists():
            raise FileExistsError(
                f"global config already exists at {GLOBAL_CONFIG_FILE}; "
                f"refusing to overwrite"
            )
        GLOBAL_CONFIG_FILE.write_text(_GLOBAL_TEMPLATE, encoding="utf-8")
        return GLOBAL_CONFIG_FILE

    if scope == "project":
        assert target is not None, "init_config(scope='project') requires a target path"
        repo = Path(target).resolve()
        if not repo.is_dir():
            raise NotADirectoryError(f"target is not a directory: {repo}")
        cfg_dir = repo / PROJECT_CONFIG_DIRNAME
        cfg_dir.mkdir(parents=True, exist_ok=True)
        project_yml = cfg_dir / PROJECT_CONFIG_FILENAME
        local_yml = cfg_dir / PROJECT_LOCAL_CONFIG_FILENAME
        gitignore = cfg_dir / PROJECT_GITIGNORE_FILENAME
        if project_yml.exists():
            raise FileExistsError(
                f"project config already exists at {project_yml}; "
                f"refusing to overwrite"
            )
        project_yml.write_text(_PROJECT_TEMPLATE, encoding="utf-8")
        if not local_yml.exists():
            local_yml.write_text(_PROJECT_LOCAL_TEMPLATE, encoding="utf-8")
        if not gitignore.exists():
            gitignore.write_text(_PROJECT_GITIGNORE, encoding="utf-8")
        return project_yml

    raise ValueError(f"unknown init scope: {scope!r} (valid: 'global', 'project')")
