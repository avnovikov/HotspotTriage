"""Validate merged configuration before analysis."""

from __future__ import annotations

from typing import Any

from hotspottriage import filtering as _filtering
from hotspottriage import normalize as _normalize
from hotspottriage import output as _output
from hotspottriage import score_metrics as _score_metrics
from .defaults import (
    _SMELL_POSITIVE_INT_CONFIG_KEYS,
    _VALID_GRANULARITY,
    _VALID_LOG_LEVELS,
)


def _validate_score_metrics(config: dict[str, Any]) -> list[Any]:
    score_metrics = config.get("score_metrics") or []
    if not isinstance(score_metrics, list) or not score_metrics:
        raise ValueError("score_metrics must be a non-empty list")
    bad = [m for m in score_metrics if m not in _score_metrics.SCORE_METRICS]
    if bad:
        raise ValueError(
            f"unknown score metric(s): {bad} "
            f"(valid: {list(_score_metrics.SCORE_METRICS)})"
        )
    return score_metrics


def _validate_format_sort_granularity_log(config: dict[str, Any]) -> None:
    fmt = config.get("format")
    if fmt not in _output.FORMATS:
        raise ValueError(
            f"unknown format: {fmt!r} (valid: {list(_output.FORMATS)})"
        )

    sort_key = config.get("sort")
    if sort_key not in _score_metrics.SORT_KEYS:
        raise ValueError(
            f"unknown sort key: {sort_key!r} (valid: {list(_score_metrics.SORT_KEYS)})"
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


def _validate_limit_and_block_workers(config: dict[str, Any]) -> None:
    limit = config.get("limit")
    if limit is not None and (not isinstance(limit, int) or limit < 0):
        raise ValueError(f"limit must be null or a non-negative int; got {limit!r}")

    workers = config.get("block_workers")
    if workers is not None and (not isinstance(workers, int) or workers < 1):
        raise ValueError(
            f"block_workers must be null or a positive int; got {workers!r}"
        )


def _validate_block_directories_exclusion(config: dict[str, Any]) -> None:
    if config.get("granularity") == "block" and config.get("directories"):
        raise ValueError("`directories` cannot be combined with `granularity: block`")


def _validate_gitignore_and_ignore_directories(config: dict[str, Any]) -> None:
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


def _validate_decay_half_life_and_smell_weight(config: dict[str, Any]) -> None:
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


def _validate_smell_default_weight(config: dict[str, Any]) -> None:
    smell_default = config.get("smell_default_weight")
    if not isinstance(smell_default, (int, float)) or not (
        0.0 <= float(smell_default) <= 1.0
    ):
        raise ValueError(
            "smell_default_weight must be a number in [0.0, 1.0]; "
            f"got {smell_default!r}"
        )


def _validate_smell_category_weights(config: dict[str, Any]) -> None:
    scw = config.get("smell_category_weights")
    if not isinstance(scw, dict) or not scw:
        raise ValueError("smell_category_weights must be a non-empty dict")
    allowed_cat = frozenset("FEWRC")
    for key, val in scw.items():
        if not isinstance(key, str) or len(key) != 1 or key.upper() not in allowed_cat:
            raise ValueError(
                "smell_category_weights keys must be a single letter in F, E, W, R, C; "
                f"got {key!r}"
            )
        if not isinstance(val, (int, float)) or not (0.0 <= float(val) <= 1.0):
            raise ValueError(
                f"smell_category_weights[{key!r}] must be a number in [0.0, 1.0]; got {val!r}"
            )


def _validate_smell_rule_weights(config: dict[str, Any]) -> None:
    srw = config.get("smell_rule_weights")
    if not isinstance(srw, dict):
        raise ValueError(
            f"smell_rule_weights must be a dict; got {type(srw).__name__}: {srw!r}"
        )
    for key, val in srw.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError(
                f"smell_rule_weights keys must be non-empty strings; got {key!r}"
            )
        if not isinstance(val, (int, float)) or not (0.0 <= float(val) <= 1.0):
            raise ValueError(
                f"smell_rule_weights[{key!r}] must be a number in [0.0, 1.0]; got {val!r}"
            )


def _validate_smell_positive_int_thresholds(config: dict[str, Any]) -> None:
    for key in _SMELL_POSITIVE_INT_CONFIG_KEYS:
        value = config.get(key)
        if not isinstance(value, int) or value < 1:
            raise ValueError(f"{key} must be a positive int; got {value!r}")


def _validate_min_sloc_for_ratio(config: dict[str, Any]) -> None:
    v = config.get("min_sloc_for_ratio")
    if not isinstance(v, int) or v < 1:
        raise ValueError(
            f"min_sloc_for_ratio must be an int >= 1 (use 1 for legacy ratio denominator); "
            f"got {v!r}"
        )


def _validate_trivial_wrapper_thresholds(config: dict[str, Any]) -> None:
    mn = config.get("smell_trivial_wrapper_min_churn_per_sloc")
    if not isinstance(mn, (int, float)) or float(mn) < 0.0:
        raise ValueError(
            "smell_trivial_wrapper_min_churn_per_sloc must be a non-negative number; "
            f"got {mn!r}"
        )


def _validate_smell_comment_ratio_and_middle_man(config: dict[str, Any]) -> None:
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


def _validate_progress_flag(config: dict[str, Any]) -> None:
    progress = config.get("progress")
    if progress is not None and not isinstance(progress, bool):
        raise ValueError(
            f"progress must be null or a boolean; got {type(progress).__name__}: {progress!r}"
        )


def _validate_similarity_metric_vs_granularity(
    config: dict[str, Any], score_metrics: list[Any]
) -> None:
    if "similarity_score" in score_metrics and config.get("granularity") != "block":
        raise ValueError(
            "score_metrics cannot include similarity_score unless granularity is block"
        )


def _validate_similarity_enabled_flag(config: dict[str, Any]) -> None:
    sim_en = config.get("similarity_enabled")
    if not isinstance(sim_en, bool):
        raise ValueError(
            f"similarity_enabled must be a boolean; got {type(sim_en).__name__}: {sim_en!r}"
        )


def _validate_similarity_threshold_value(config: dict[str, Any]) -> None:
    st = config.get("similarity_threshold")
    if not isinstance(st, (int, float)) or not (0 < st <= 100):
        raise ValueError(
            f"similarity_threshold must be between 0 and 100 (exclusive 0); got {st!r}"
        )


_SIMILARITY_BAND_KEYS = (
    "similarity_band_high",
    "similarity_band_medium",
    "similarity_band_low",
)


def _validate_similarity_band_bounds(config: dict[str, Any]) -> None:
    for key in _SIMILARITY_BAND_KEYS:
        v = config.get(key)
        if not isinstance(v, (int, float)) or not (0 < v <= 100):
            raise ValueError(f"{key} must be a number in (0, 100]; got {v!r}")


def _validate_similarity_band_ordering(config: dict[str, Any]) -> None:
    bh = float(config["similarity_band_high"])
    bm = float(config["similarity_band_medium"])
    bl = float(config["similarity_band_low"])
    if not (bh >= bm >= bl):
        raise ValueError(
            "similarity_band_high >= similarity_band_medium >= similarity_band_low is required"
        )


def _validate_similarity_max_pairwise_blocks_value(config: dict[str, Any]) -> None:
    smb = config.get("similarity_max_pairwise_blocks")
    if not isinstance(smb, int) or smb < 2:
        raise ValueError(
            f"similarity_max_pairwise_blocks must be an int >= 2; got {smb!r}"
        )


def _validate_similarity_aggregate_row_flag(config: dict[str, Any]) -> None:
    sar = config.get("similarity_aggregate_row")
    if not isinstance(sar, bool):
        raise ValueError(
            f"similarity_aggregate_row must be a boolean; got {type(sar).__name__}: {sar!r}"
        )


def _validate_similarity_settings(config: dict[str, Any]) -> None:
    _validate_similarity_enabled_flag(config)
    _validate_similarity_threshold_value(config)
    _validate_similarity_band_bounds(config)
    _validate_similarity_band_ordering(config)
    _validate_similarity_max_pairwise_blocks_value(config)
    _validate_similarity_aggregate_row_flag(config)


def _validate_proposed_models(config: dict[str, Any]) -> None:
    models = config.get("proposed_models")
    if not isinstance(models, dict):
        raise ValueError(
            f"proposed_models must be a dict; got {type(models).__name__}: {models!r}"
        )
    required_bands = ("low", "medium", "high", "critical")
    for band in required_bands:
        if band not in models:
            raise ValueError(
                f"proposed_models missing required key {band!r}; "
                f"expected keys: {list(required_bands)}"
            )
        value = models[band]
        if not isinstance(value, str):
            raise ValueError(
                f"proposed_models[{band!r}] must be a string; got {type(value).__name__}: {value!r}"
            )


def _dashboard_section_mapping(config: dict[str, Any]) -> dict[str, Any]:
    d = config.get("dashboard")
    if not isinstance(d, dict):
        raise ValueError(
            f"dashboard must be a dict; got {type(d).__name__}: {d!r}"
        )
    return d


def _validate_dashboard_enabled(d: dict[str, Any]) -> None:
    if not isinstance(d.get("enabled"), bool):
        raise ValueError(
            "dashboard.enabled must be a boolean "
            f"(got {type(d.get('enabled')).__name__}: {d.get('enabled')!r})"
        )


def _validate_dashboard_host(d: dict[str, Any]) -> None:
    host = d.get("host")
    if not isinstance(host, str) or not host.strip():
        raise ValueError(f"dashboard.host must be a non-empty string; got {host!r}")


def _validate_dashboard_base_port(d: dict[str, Any]) -> None:
    bp = d.get("base_port")
    if not isinstance(bp, int) or not (1 <= bp <= 65535):
        raise ValueError(
            f"dashboard.base_port must be an int in [1, 65535]; got {bp!r}"
        )


def _validate_dashboard_open_on_start(d: dict[str, Any]) -> None:
    if not isinstance(d.get("open_on_start"), bool):
        raise ValueError(
            "dashboard.open_on_start must be a boolean "
            f"(got {type(d.get('open_on_start')).__name__}: {d.get('open_on_start')!r})"
        )


def _validate_dashboard_max_log_records(d: dict[str, Any]) -> None:
    ml = d.get("max_log_records")
    if not isinstance(ml, int) or ml < 1:
        raise ValueError(
            f"dashboard.max_log_records must be a positive int; got {ml!r}"
        )


def _validate_dashboard_default_target(d: dict[str, Any]) -> None:
    dt = d.get("default_target")
    if not isinstance(dt, str):
        raise ValueError(
            f"dashboard.default_target must be a string; got {type(dt).__name__}: {dt!r}"
        )


def _validate_dashboard_section(config: dict[str, Any]) -> None:
    d = _dashboard_section_mapping(config)
    _validate_dashboard_enabled(d)
    _validate_dashboard_host(d)
    _validate_dashboard_base_port(d)
    _validate_dashboard_open_on_start(d)
    _validate_dashboard_max_log_records(d)
    _validate_dashboard_default_target(d)


def validate(config: dict[str, Any]) -> None:
    """Validate a fully-merged config. Raises ValueError on the first problem.

    Defensive check: catches typos / bad values from any layer (file or CLI)
    before they reach the analysis pipeline, where the failure mode is harder
    to debug ("why is my output empty?").
    """
    score_metrics = _validate_score_metrics(config)
    _validate_format_sort_granularity_log(config)
    _validate_limit_and_block_workers(config)
    _validate_block_directories_exclusion(config)
    _validate_gitignore_and_ignore_directories(config)
    _validate_decay_half_life_and_smell_weight(config)
    _validate_smell_default_weight(config)
    _validate_smell_category_weights(config)
    _validate_smell_rule_weights(config)
    _validate_smell_positive_int_thresholds(config)
    _validate_min_sloc_for_ratio(config)
    _validate_trivial_wrapper_thresholds(config)
    _validate_smell_comment_ratio_and_middle_man(config)
    _validate_progress_flag(config)
    _validate_similarity_metric_vs_granularity(config, score_metrics)
    _validate_similarity_settings(config)

    _validate_dashboard_section(config)
    _validate_proposed_models(config)

    _normalize.validate_metric_normalization(config)

    from hotspottriage import score as _score_validation

    _score_validation.validate_score_aggregation(config)
