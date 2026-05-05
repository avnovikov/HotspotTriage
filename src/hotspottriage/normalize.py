"""Configurable normalization of raw metrics to ``[0.0, 1.0]`` (higher = worse).

Used to compare heterogeneous metrics on a common scale. Configuration lives
under ``metric_normalization`` in merged YAML / :data:`hotspottriage.config.DEFAULTS`.
"""
from __future__ import annotations

from typing import Any

_VALID_METHODS = frozenset({"identity", "zscore", "piecewise", "inverse_piecewise"})


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _piecewise_sorted_knots(
    breakpoints: list[list[float]],
    *,
    invert_y: bool,
) -> list[tuple[float, float]]:
    """Return ``(x, y)`` knots sorted by ``x`` with ``y`` non-decreasing."""
    if len(breakpoints) < 2:
        raise ValueError("piecewise breakpoints need at least two [raw, norm] pairs")
    knots: list[tuple[float, float]] = []
    for i, pt in enumerate(breakpoints):
        if not isinstance(pt, (list, tuple)) or len(pt) != 2:
            raise ValueError(f"breakpoint {i} must be a pair [raw, norm]; got {pt!r}")
        x, y = float(pt[0]), float(pt[1])
        if invert_y:
            y = 1.0 - y
        knots.append((x, y))
    knots.sort(key=lambda t: t[0])
    xs = [k[0] for k in knots]
    if len(set(xs)) != len(xs):
        raise ValueError("piecewise breakpoints must have unique raw values")
    ys = [k[1] for k in knots]
    for a, b in zip(ys, ys[1:]):
        if b + 1e-12 < a:
            raise ValueError(
                "after sorting by raw, norm values must be non-decreasing "
                f"(got sequence {ys})"
            )
    return knots


def _piecewise_eval(value: float, knots: list[tuple[float, float]]) -> float:
    """Linear interpolation; extrapolate flat beyond endpoints."""
    x = float(value)
    x0, y0 = knots[0]
    if x <= x0:
        return y0
    xn, yn = knots[-1]
    if x >= xn:
        return yn
    for (xa, ya), (xb, yb) in zip(knots, knots[1:]):
        if xa <= x <= xb:
            if xb == xa:
                return ya
            t = (x - xa) / (xb - xa)
            return ya + t * (yb - ya)
    return yn


def normalize(value: float | int, config: dict[str, Any]) -> float:
    """Map a single raw metric to ``[0.0, 1.0]`` using ``config['method']``.

    ``config`` must include ``method``: ``identity`` | ``zscore`` | ``piecewise`` |
    ``inverse_piecewise``. Method-specific keys are documented in
    :func:`validate_metric_normalization`.
    """
    method = str(config.get("method", "identity"))
    if method not in _VALID_METHODS:
        raise ValueError(
            f"unknown normalization method {method!r} "
            f"(valid: {sorted(_VALID_METHODS)})"
        )
    v = float(value)

    if method == "identity":
        return _clamp01(v)

    if method == "zscore":
        center = float(config.get("center", 0.0))
        scale = float(config.get("scale", 1.0))
        if scale == 0.0:
            raise ValueError("zscore scale must be non-zero")
        clamp = config.get("clamp")
        if not isinstance(clamp, (list, tuple)) or len(clamp) != 2:
            raise ValueError("zscore requires clamp: [low, high]")
        c_lo, c_hi = float(clamp[0]), float(clamp[1])
        if c_hi <= c_lo:
            raise ValueError(f"zscore clamp must have low < high; got {clamp!r}")
        z = (v - center) / scale
        cz = max(c_lo, min(c_hi, z))
        return _clamp01((cz - c_lo) / (c_hi - c_lo))

    if method == "piecewise":
        bps = config.get("breakpoints")
        if not isinstance(bps, list):
            raise ValueError("piecewise requires breakpoints: list of [raw, norm] pairs")
        knots = _piecewise_sorted_knots(bps, invert_y=False)
        return _clamp01(_piecewise_eval(v, knots))

    if method == "inverse_piecewise":
        bps = config.get("breakpoints")
        if not isinstance(bps, list):
            raise ValueError(
                "inverse_piecewise requires breakpoints: list of [raw, norm] pairs"
            )
        knots = _piecewise_sorted_knots(bps, invert_y=True)
        return _clamp01(_piecewise_eval(v, knots))

    raise AssertionError(f"unhandled method {method}")


def normalize_record(record: dict[str, Any], norm_config: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy of ``record`` plus ``norm_<field>`` for each rule.

    Keys in ``norm_config`` whose values are mapping configs are applied when
    the same key exists in ``record``. Keys starting with ``"_"`` are skipped
    (reserved for batch metadata extensions).
    """
    out: dict[str, Any] = dict(record)
    for key, cfg in norm_config.items():
        if key.startswith("_") or not isinstance(cfg, dict):
            continue
        if key not in record:
            continue
        raw = record[key]
        if raw is None:
            continue
        try:
            fv = float(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        out[f"norm_{key}"] = normalize(fv, cfg)
    return out


def validate_metric_normalization(cfg: dict[str, Any]) -> None:
    """Raise ``ValueError`` if ``metric_normalization`` is structurally invalid."""
    root = cfg.get("metric_normalization")
    if root is None:
        return
    if not isinstance(root, dict):
        raise ValueError(
            f"metric_normalization must be a dict; got {type(root).__name__}: {root!r}"
        )
    for metric, sub in root.items():
        if not isinstance(metric, str) or not metric.strip():
            raise ValueError(f"metric_normalization metric key must be a non-empty string; got {metric!r}")
        if not isinstance(sub, dict):
            raise ValueError(
                f"metric_normalization[{metric!r}] must be a dict; got {type(sub).__name__}"
            )
        method = sub.get("method")
        if method not in _VALID_METHODS:
            raise ValueError(
                f"metric_normalization[{metric!r}].method must be one of "
                f"{sorted(_VALID_METHODS)}; got {method!r}"
            )
        # Touch logic by running a representative value (catches bad breakpoints).
        if method == "zscore":
            normalize(0.0, sub)
        elif method == "piecewise":
            bps = sub.get("breakpoints")
            if not isinstance(bps, list) or len(bps) < 2:
                raise ValueError(
                    f"metric_normalization[{metric!r}] needs at least two breakpoints"
                )
            xs = sorted(float(p[0]) for p in bps)
            mid = (xs[0] + xs[-1]) / 2.0
            normalize(mid, sub)
        elif method == "inverse_piecewise":
            bps = sub.get("breakpoints")
            if not isinstance(bps, list) or len(bps) < 2:
                raise ValueError(
                    f"metric_normalization[{metric!r}] needs at least two breakpoints"
                )
            xs = sorted(float(p[0]) for p in bps)
            mid = (xs[0] + xs[-1]) / 2.0
            normalize(mid, sub)
        else:
            normalize(0.5, sub)
