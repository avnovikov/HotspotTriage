"""Template generation for ``hotspottriage init`` (global and project scopes)."""

from __future__ import annotations

from pathlib import Path

from .defaults import (
    PROJECT_CONFIG_DIRNAME,
    PROJECT_CONFIG_FILENAME,
    PROJECT_GITIGNORE_FILENAME,
    PROJECT_LOCAL_CONFIG_FILENAME,
)

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

# Smell severity (0–1) per finding: rule id in smell_rule_weights, else Pylint
# category letter (F/E/W/R/C) via smell_category_weights, else smell_default_weight.
# smell_default_weight: 0.4
# smell_category_weights: {F: 1.0, E: 0.85, W: 0.6, R: 0.45, C: 0.2}
# smell_rule_weights: {long_method: 0.7, dead_code: 0.65, ...}

# Optional: map raw metrics to [0,1] (higher = worse); see hotspottriage.normalize.
# metric_normalization:
#   cyclomatic: {method: piecewise, breakpoints: [[1, 0.0], [20, 1.0]]}

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


def _init_global_config() -> Path:
    from hotspottriage import config as _cfg

    _cfg.GLOBAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if _cfg.GLOBAL_CONFIG_FILE.exists():
        raise FileExistsError(
            f"global config already exists at {_cfg.GLOBAL_CONFIG_FILE}; "
            f"refusing to overwrite"
        )
    _cfg.GLOBAL_CONFIG_FILE.write_text(_GLOBAL_TEMPLATE, encoding="utf-8")
    return _cfg.GLOBAL_CONFIG_FILE


def _init_project_config(target: Path) -> Path:
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


def init_config(scope: str, target: Path | None = None) -> Path:
    """Scaffold a config template. Returns the primary file written.

    `scope` is 'global' or 'project'. For project scope, `target` must be
    the repo root.
    """
    if scope == "global":
        return _init_global_config()

    if scope == "project":
        assert target is not None, "init_config(scope='project') requires a target path"
        return _init_project_config(target)

    raise ValueError(f"unknown init scope: {scope!r} (valid: 'global', 'project')")
