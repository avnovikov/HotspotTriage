"""Tests for hotspottriage.normalize."""
from __future__ import annotations

import pytest

from hotspottriage import config as _config
from hotspottriage import normalize as norm


def test_identity_clamps_to_unit_interval():
    assert norm.normalize(0.5, {"method": "identity"}) == pytest.approx(0.5)
    assert norm.normalize(1.2, {"method": "identity"}) == pytest.approx(1.0)
    assert norm.normalize(-0.1, {"method": "identity"}) == pytest.approx(0.0)


def test_zscore_maps_clamped_range_to_zero_one():
    cfg = {"method": "zscore", "center": 0.0, "scale": 1.0, "clamp": [-2.5, 2.5]}
    assert norm.normalize(0.0, cfg) == pytest.approx(0.5)
    assert norm.normalize(-2.5, cfg) == pytest.approx(0.0)
    assert norm.normalize(2.5, cfg) == pytest.approx(1.0)
    assert norm.normalize(100.0, cfg) == pytest.approx(1.0)


def test_zscore_rejects_bad_clamp():
    with pytest.raises(ValueError, match="clamp"):
        norm.normalize(0.0, {"method": "zscore", "center": 0.0, "scale": 1.0, "clamp": [1, 0]})
    with pytest.raises(ValueError, match="scale"):
        norm.normalize(0.0, {"method": "zscore", "center": 0.0, "scale": 0.0, "clamp": [0, 1]})


def test_piecewise_interpolates_and_extrapolates():
    cfg = {
        "method": "piecewise",
        "breakpoints": [[1, 0.0], [5, 0.1], [10, 0.5], [20, 1.0]],
    }
    assert norm.normalize(1.0, cfg) == pytest.approx(0.0)
    assert norm.normalize(20.0, cfg) == pytest.approx(1.0)
    assert norm.normalize(7.5, cfg) == pytest.approx(0.3)  # midpoint between (5,0.1) and (10,0.5)
    assert norm.normalize(0.0, cfg) == pytest.approx(0.0)
    assert norm.normalize(100.0, cfg) == pytest.approx(1.0)


def test_piecewise_accepts_unsorted_breakpoints():
    cfg = {
        "method": "piecewise",
        "breakpoints": [[20, 1.0], [1, 0.0], [10, 0.5], [5, 0.1]],
    }
    assert norm.normalize(7.5, cfg) == pytest.approx(0.3)


def test_piecewise_rejects_non_monotonic_norm():
    cfg = {"method": "piecewise", "breakpoints": [[0, 0.0], [5, 1.0], [10, 0.5]]}
    with pytest.raises(ValueError, match="non-decreasing"):
        norm.normalize(5.0, cfg)


def test_inverse_piecewise_flips_issue_maintainability_defaults():
    cfg = _config.DEFAULTS["metric_normalization"]["maintainability"]
    # Stored maintainability is "higher = worse"; worst bucket should map near 1.
    assert norm.normalize(85.0, cfg) == pytest.approx(1.0)
    assert norm.normalize(20.0, cfg) == pytest.approx(0.0)


def test_normalize_unknown_method():
    with pytest.raises(ValueError, match="unknown normalization"):
        norm.normalize(1.0, {"method": "bogus"})


def test_normalize_record_adds_prefixed_fields_and_preserves_input():
    record = {"cyclomatic": 7, "path": "x.py"}
    norm_cfg = {
        "cyclomatic": {
            "method": "piecewise",
            "breakpoints": [[1, 0.0], [5, 0.1], [10, 0.5], [20, 1.0]],
        },
        "_meta": {"ignored": True},
    }
    out = norm.normalize_record(record, norm_cfg)
    assert "norm_cyclomatic" in out
    # raw=7 lies between 5 and 10: 0.1 + (2/5)*(0.5-0.1) = 0.26
    assert out["norm_cyclomatic"] == pytest.approx(0.26)
    assert out["path"] == "x.py"
    assert "norm_cyclomatic" not in record


def test_validate_metric_normalization_accepts_defaults():
    norm.validate_metric_normalization(dict(_config.DEFAULTS))


def test_validate_metric_normalization_rejects_bad_method():
    cfg = {
        **_config.DEFAULTS,
        "metric_normalization": {"cyclomatic": {"method": "nope"}},
    }
    with pytest.raises(ValueError, match="method"):
        norm.validate_metric_normalization(cfg)
