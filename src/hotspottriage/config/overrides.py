"""CLI ``argparse`` overrides layered on merged YAML config."""

from __future__ import annotations

import argparse
from copy import deepcopy
from typing import Any

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


def _cli_bool_override_sets_true(out: dict[str, Any], cfg_key: str, val: Any) -> bool:
    """store_true semantics: True writes True; False leaves config unchanged."""
    if not isinstance(val, bool):
        return False
    if val:
        out[cfg_key] = True
    return True


def _cli_special_mapped_override(out: dict[str, Any], cfg_key: str, val: Any) -> bool:
    """CSV/list parsing for keys that do not take raw CLI values."""
    if cfg_key == "score_metrics":
        out[cfg_key] = _parse_csv(val)
        return True
    if cfg_key == "filter":
        csv_val = _parse_csv(val)
        if csv_val:
            out[cfg_key] = csv_val
        return True
    return False


def _apply_mapped_cli_overrides(out: dict[str, Any], args: argparse.Namespace) -> None:
    for cli_key, cfg_key in _CLI_TO_CONFIG.items():
        if not hasattr(args, cli_key):
            continue
        val = getattr(args, cli_key)
        if val is None:
            continue
        if _cli_bool_override_sets_true(out, cfg_key, val):
            continue
        if _cli_special_mapped_override(out, cfg_key, val):
            continue
        out[cfg_key] = val


def _apply_no_respect_gitignore_override(out: dict[str, Any], args: argparse.Namespace) -> None:
    if getattr(args, "no_respect_gitignore", None):
        out["respect_gitignore"] = False


def _apply_ignore_dir_override(out: dict[str, Any], args: argparse.Namespace) -> None:
    extra_dirs = getattr(args, "ignore_dir", None)
    if extra_dirs:
        merged_dirs = list(out.get("ignore_directories") or [])
        merged_dirs.extend(extra_dirs)
        out["ignore_directories"] = merged_dirs


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
    _apply_mapped_cli_overrides(out, args)
    _apply_no_respect_gitignore_override(out, args)
    _apply_ignore_dir_override(out, args)
    return out
