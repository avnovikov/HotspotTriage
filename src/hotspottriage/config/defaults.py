"""Built-in defaults and path constants for layered YAML configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

GLOBAL_CONFIG_DIR = Path.home() / ".hotspottriage"
GLOBAL_CONFIG_FILE = GLOBAL_CONFIG_DIR / "config.yml"

PROJECT_CONFIG_DIRNAME = ".hotspottriage"
PROJECT_CONFIG_FILENAME = "project.yml"
PROJECT_LOCAL_CONFIG_FILENAME = "project.local.yml"
DASHBOARD_CONFIG_PATCH_FILENAME = "dashboard_config_patch.yml"
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
    # Minimum SLOC used as denominator for churn_per_sloc / decayed_churn_per_sloc
    # (actual sloc is unchanged). Reduces tiny-function ratio spikes; set to 1 to
    # match legacy churn / raw sloc for sloc >= 1.
    "min_sloc_for_ratio": 6,
    # Block-only heuristic: single-return delegation wrappers (see smell.py).
    "smell_trivial_wrapper_max_sloc": 4,
    "smell_trivial_wrapper_min_churn_per_sloc": 5.0,
    # Smell severity (0–1) for weighted burden: rule id → weight (overrides category).
    "smell_default_weight": 0.4,
    "smell_category_weights": {
        "F": 1.0,
        "E": 0.85,
        "W": 0.6,
        "R": 0.45,
        "C": 0.2,
    },
    "smell_rule_weights": {
        "duplicate_code": 0.8,
        "switch_statements": 0.75,
        "long_method": 0.7,
        "too_many_statements": 0.7,
        "long_parameter_list": 0.6,
        "too_many_locals": 0.55,
        "large_class": 0.75,
        "dead_code": 0.65,
        "lazy_class": 0.45,
        "unused_parameters": 0.55,
        "data_class": 0.45,
        "middle_man": 0.5,
        "speculative_generality": 0.55,
        "excessive_comments": 0.25,
        "large_comment_block": 0.3,
        "trivial_wrapper": 0.45,
    },
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
    # Per-metric normalization to [0,1] (higher = worse); see normalize.py.
    "metric_normalization": {
        "normalized_sloc": {
            "method": "zscore",
            "center": 0.0,
            "scale": 1.0,
            "clamp": [-2.5, 2.5],
        },
        "sloc": {
            "method": "zscore",
            "center": 0.0,
            "scale": 1.0,
            "clamp": [-2.5, 2.5],
        },
        "cyclomatic": {
            "method": "piecewise",
            "breakpoints": [[1, 0.0], [5, 0.1], [10, 0.5], [20, 1.0]],
        },
        "halstead": {
            "method": "piecewise",
            "breakpoints": [[20, 0.0], [100, 0.4], [200, 0.7], [400, 1.0]],
        },
        "maintainability": {
            "method": "inverse_piecewise",
            "breakpoints": [[85, 0.0], [65, 0.4], [40, 0.8], [20, 1.0]],
        },
        "churn": {
            "method": "piecewise",
            "breakpoints": [[0, 0.0], [5, 0.3], [20, 0.7], [50, 1.0]],
        },
        "churn_per_sloc": {
            "method": "piecewise",
            "breakpoints": [[0.0, 0.0], [0.10, 0.3], [0.30, 0.7], [0.60, 1.0]],
        },
        "decayed_churn": {
            "method": "piecewise",
            "breakpoints": [[0, 0.0], [3, 0.3], [10, 0.7], [25, 1.0]],
        },
        "decayed_churn_per_sloc": {
            "method": "piecewise",
            "breakpoints": [[0.0, 0.0], [0.05, 0.3], [0.20, 0.7], [0.40, 1.0]],
        },
        "smell_count": {
            "method": "piecewise",
            "breakpoints": [[0, 0.0], [2, 0.3], [5, 0.7], [10, 1.0]],
        },
        "smell_severity": {
            "method": "piecewise",
            "breakpoints": [[0, 0.0], [0.5, 0.25], [1.0, 0.5], [2.0, 0.8], [5.0, 1.0]],
        },
        "match_count": {
            "method": "piecewise",
            "breakpoints": [[0, 0.0], [1, 0.3], [3, 0.7], [5, 1.0]],
        },
        "similarity_score": {"method": "piecewise", "breakpoints": [[0, 0.0], [100, 1.0]]},
    },
    # Block-only: weighted combination of normalized subscores into score (0–1).
    # Ignored for file-level runs. See hotspottriage.score.compute_score.
    "score_aggregation": {
        "enabled": True,
        "complexity_weights": {
            "cyclomatic": 0.40,
            "halstead": 0.25,
            "normalized_sloc": 0.35,
        },
        "churn_weights": {
            "churn": 0.10,
            "churn_per_sloc": 0.20,
            "decayed_churn": 0.25,
            "decayed_churn_per_sloc": 0.45,
        },
        "smell_weights": {
            "smell_count": 0.50,
            "smell_severity": 0.50,
        },
        "similarity_weights": {
            "similarity_score": 0.80,
            "match_count": 0.20,
        },
        "final_weights": {
            "complexity_burden": 0.30,
            "churn_burden": 0.25,
            "maintainability_burden": 0.20,
            "smell_burden": 0.15,
            "similarity_burden": 0.10,
        },
        "band_edges": [0.30, 0.60, 0.80],
        "band_names": ["low", "medium", "high", "critical"],
    },
    # MCP web dashboard (see dashboard/server.py); overridden by hotspottriage-mcp flags.
    "dashboard": {
        "enabled": True,
        "host": "127.0.0.1",
        "base_port": 9123,
        "open_on_start": False,
        "max_log_records": 1000,
        "default_target": "",
    },
    # MCP-only: recommended free-text model names by risk band.
    "proposed_models": {
        "low": "Auto",
        "medium": "Auto",
        "high": "Auto",
        "critical": "Auto",
    },
}

_VALID_LOG_LEVELS = ("debug", "info", "warning", "error")
_VALID_GRANULARITY = ("file", "block")

_SMELL_POSITIVE_INT_CONFIG_KEYS: tuple[str, ...] = (
    "smell_max_statements",
    "smell_max_attributes",
    "smell_max_public_methods",
    "smell_max_args",
    "smell_max_branches",
    "smell_min_public_methods",
    "smell_max_comment_block_lines",
    "smell_data_class_min_attributes",
    "smell_speculative_generality_min_hits",
    "smell_trivial_wrapper_max_sloc",
)
