"""YAML loading, deep merge, and config layer resolution."""

from __future__ import annotations

import importlib.metadata
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from .defaults import (
    DASHBOARD_CONFIG_PATCH_FILENAME,
    DEFAULTS,
    PROJECT_CONFIG_DIRNAME,
    PROJECT_CONFIG_FILENAME,
    PROJECT_LOCAL_CONFIG_FILENAME,
)


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
    # Resolve global paths via the public package so tests can monkeypatch
    # ``hotspottriage.config.GLOBAL_CONFIG_*`` (same as monolithic config.py).
    from hotspottriage import config as _cfg

    if use_global and _cfg.GLOBAL_CONFIG_FILE.is_file():
        paths.append(_cfg.GLOBAL_CONFIG_FILE)
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


def merge_dashboard_config_patch(
    repo: Path, cfg: dict[str, Any]
) -> dict[str, Any]:
    """Deep-merge ``<repo>/.hotspottriage/dashboard_config_patch.yml`` into *cfg*.

    Same file and semantics as :func:`hotspottriage.mcp.analyze_config.build_analyze_config` for a
    local target: dashboard UI / heatmap tuning for ``metric_normalization``,
    ``score_aggregation``, and ``proposed_models``. Missing or empty files are
    a no-op. Returns a new dict; *cfg* is not mutated.
    """
    patch_path = (
        Path(repo).resolve()
        / PROJECT_CONFIG_DIRNAME
        / DASHBOARD_CONFIG_PATCH_FILENAME
    )
    if not patch_path.is_file():
        return deepcopy(cfg)
    layer = _read_yaml(patch_path)
    if not layer:
        return deepcopy(cfg)
    _reject_unknown_keys(layer, patch_path)
    return _deep_merge(cfg, layer)


def load_analyze_config_for_local_repo(
    repo: Path,
    *,
    explicit: Path | None = None,
) -> dict[str, Any]:
    """Merged config for scoring and score explanations on a local checkout.

    Single entry point for CLI analyze, MCP local ``analyze``, dashboard
    heatmap derivation, lazy ``block_narrative``, and cache-generation overrides
    so ``metric_normalization``, ``score_aggregation``, ``proposed_models``, and
    related keys stay aligned for the same repository path.

    Layers: ``DEFAULTS`` ← ``project.yml`` / ``project.local.yml`` ← *explicit*
    ``--config`` file ← ``<repo>/.hotspottriage/dashboard_config_patch.yml``.
    Skips global ``~/.hotspottriage/config.yml`` (``use_global=False``).
    """
    root = Path(repo).expanduser().resolve()
    merged = load_config(
        root,
        explicit=explicit,
        use_global=False,
        use_project=True,
    )
    return merge_dashboard_config_patch(root, merged)


def apply_mcp_dashboard_cli_overrides(
    config: dict[str, Any],
    *,
    no_dashboard: bool = False,
    dashboard_port: int | None = None,
    dashboard_host: str | None = None,
    open_browser: bool = False,
) -> dict[str, Any]:
    """Return a copy of ``config`` with MCP ``hotspottriage-mcp`` dashboard flags applied."""
    out = deepcopy(config)
    dash = dict(out.get("dashboard") or deepcopy(DEFAULTS["dashboard"]))
    if no_dashboard:
        dash["enabled"] = False
    if dashboard_port is not None:
        dash["base_port"] = int(dashboard_port)
    if dashboard_host is not None:
        h = str(dashboard_host).strip()
        if not h:
            raise ValueError("dashboard_host must be a non-empty string")
        dash["host"] = h
    if open_browser:
        dash["open_on_start"] = True
    out["dashboard"] = dash
    return out


def to_dashboard_snapshot(
    merged_config: dict[str, Any],
    *,
    project_path: str | None = None,
) -> dict[str, Any]:
    """JSON-serializable overview for the web dashboard ``/api/config`` endpoint."""
    return {
        "version": importlib.metadata.version("hotspottriage"),
        "project": {"path": project_path},
        "granularity": merged_config.get("granularity"),
        "score_metrics": list(merged_config.get("score_metrics") or []),
        "score_aggregation": deepcopy(merged_config.get("score_aggregation")),
        "metric_normalization": deepcopy(merged_config.get("metric_normalization")),
        "similarity_enabled": merged_config.get("similarity_enabled"),
        "decay_half_life": merged_config.get("decay_half_life"),
        "dashboard": deepcopy(merged_config.get("dashboard") or {}),
        "proposed_models": deepcopy(merged_config.get("proposed_models") or {}),
    }
