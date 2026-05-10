"""Layered YAML configuration for HotspotTriage.

Resolution order (last wins) for :func:`load_config`:

    code DEFAULTS
      -> ~/.hotspottriage/config.yml          (global, per user; optional via *use_global*)
      -> <repo>/.hotspottriage/project.yml    (per project, versioned)
      -> <repo>/.hotspottriage/project.local.yml (per machine, gitignored)
      -> --config <PATH>                      (explicit override file)

CLI ``analyze`` and MCP local ``analyze`` call ``load_config`` with
``use_global=False``, then merge ``dashboard_config_patch.yml`` via
:func:`merge_dashboard_config_patch`, then apply MCP tool arguments or CLI
flags (not part of ``load_config`` itself).

A layer only needs to specify the keys it wants to override; missing keys fall
through to the next lower layer.

This package is the single source of truth for default values; CLI argparse
defaults are intentionally `None` sentinels so we can distinguish "user passed
this flag" from "user did not pass it".
"""
from __future__ import annotations

from .defaults import (
    DASHBOARD_CONFIG_PATCH_FILENAME,
    DEFAULTS,
    GLOBAL_CONFIG_DIR,
    GLOBAL_CONFIG_FILE,
    PROJECT_CONFIG_DIRNAME,
    PROJECT_CONFIG_FILENAME,
    PROJECT_GITIGNORE_FILENAME,
    PROJECT_LOCAL_CONFIG_FILENAME,
    _SMELL_POSITIVE_INT_CONFIG_KEYS,
    _VALID_GRANULARITY,
    _VALID_LOG_LEVELS,
)
from .loading import (
    apply_mcp_dashboard_cli_overrides,
    discover_config_paths,
    load_analyze_config_for_local_repo,
    load_config,
    merge_dashboard_config_patch,
    to_dashboard_snapshot,
    _deep_merge,
    _read_yaml,
    _reject_unknown_keys,
)
from .overrides import (
    apply_cli_overrides,
    _apply_ignore_dir_override,
    _apply_mapped_cli_overrides,
    _apply_no_respect_gitignore_override,
    _CLI_TO_CONFIG,
    _cli_bool_override_sets_true,
    _cli_special_mapped_override,
    _parse_csv,
)
from .scaffolding import init_config
from .validation import (
    validate,
    _dashboard_section_mapping,
    _validate_block_directories_exclusion,
    _validate_dashboard_base_port,
    _validate_dashboard_default_target,
    _validate_dashboard_enabled,
    _validate_dashboard_host,
    _validate_dashboard_max_log_records,
    _validate_dashboard_open_on_start,
    _validate_dashboard_section,
    _validate_decay_half_life_and_smell_weight,
    _validate_format_sort_granularity_log,
    _validate_gitignore_and_ignore_directories,
    _validate_limit_and_block_workers,
    _validate_min_sloc_for_ratio,
    _validate_progress_flag,
    _validate_proposed_models,
    _validate_score_metrics,
    _validate_similarity_aggregate_row_flag,
    _validate_similarity_band_bounds,
    _validate_similarity_band_ordering,
    _validate_similarity_enabled_flag,
    _validate_similarity_max_pairwise_blocks_value,
    _validate_similarity_metric_vs_granularity,
    _validate_similarity_settings,
    _validate_similarity_threshold_value,
    _validate_smell_category_weights,
    _validate_smell_comment_ratio_and_middle_man,
    _validate_smell_default_weight,
    _validate_smell_positive_int_thresholds,
    _validate_smell_rule_weights,
    _validate_trivial_wrapper_thresholds,
)

__all__ = [
    "DASHBOARD_CONFIG_PATCH_FILENAME",
    "DEFAULTS",
    "GLOBAL_CONFIG_DIR",
    "GLOBAL_CONFIG_FILE",
    "PROJECT_CONFIG_DIRNAME",
    "PROJECT_CONFIG_FILENAME",
    "PROJECT_GITIGNORE_FILENAME",
    "PROJECT_LOCAL_CONFIG_FILENAME",
    "_SMELL_POSITIVE_INT_CONFIG_KEYS",
    "_VALID_GRANULARITY",
    "_VALID_LOG_LEVELS",
    "apply_cli_overrides",
    "apply_mcp_dashboard_cli_overrides",
    "discover_config_paths",
    "init_config",
    "load_analyze_config_for_local_repo",
    "load_config",
    "merge_dashboard_config_patch",
    "to_dashboard_snapshot",
    "validate",
    "_CLI_TO_CONFIG",
    "_apply_ignore_dir_override",
    "_apply_mapped_cli_overrides",
    "_apply_no_respect_gitignore_override",
    "_cli_bool_override_sets_true",
    "_cli_special_mapped_override",
    "_dashboard_section_mapping",
    "_deep_merge",
    "_parse_csv",
    "_read_yaml",
    "_reject_unknown_keys",
    "_validate_block_directories_exclusion",
    "_validate_dashboard_base_port",
    "_validate_dashboard_default_target",
    "_validate_dashboard_enabled",
    "_validate_dashboard_host",
    "_validate_dashboard_max_log_records",
    "_validate_dashboard_open_on_start",
    "_validate_dashboard_section",
    "_validate_decay_half_life_and_smell_weight",
    "_validate_format_sort_granularity_log",
    "_validate_gitignore_and_ignore_directories",
    "_validate_limit_and_block_workers",
    "_validate_min_sloc_for_ratio",
    "_validate_progress_flag",
    "_validate_proposed_models",
    "_validate_score_metrics",
    "_validate_similarity_aggregate_row_flag",
    "_validate_similarity_band_bounds",
    "_validate_similarity_band_ordering",
    "_validate_similarity_enabled_flag",
    "_validate_similarity_max_pairwise_blocks_value",
    "_validate_similarity_metric_vs_granularity",
    "_validate_similarity_settings",
    "_validate_similarity_threshold_value",
    "_validate_smell_category_weights",
    "_validate_smell_comment_ratio_and_middle_man",
    "_validate_smell_default_weight",
    "_validate_smell_positive_int_thresholds",
    "_validate_smell_rule_weights",
    "_validate_trivial_wrapper_thresholds",
]
