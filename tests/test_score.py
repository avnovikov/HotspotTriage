"""Tests for hotspottriage.score aggregated block scoring."""
from __future__ import annotations

import copy

import pytest

from hotspottriage.config import DEFAULTS
from hotspottriage.score import (
    compute_score,
    effective_score_aggregation,
    score_aggregation_enabled,
    validate_score_aggregation,
)


def _neutral_record() -> dict:
    return {
        "normalized_sloc": 0.0,
        "cyclomatic": 1,
        "halstead": 20,
        "maintainability": 85,
        "churn": 0,
        "churn_per_sloc": 0.0,
        "decayed_churn": 0.0,
        "decayed_churn_per_sloc": 0.0,
        "smell_count": 0.0,
        "smell_severity": 0.0,
        "similarity_score": 0.0,
        "match_count": 0.0,
    }


def test_compute_score_returns_subscores_and_band():
    cfg = copy.deepcopy(DEFAULTS)
    out = compute_score(_neutral_record(), cfg, similarity_available=True)
    assert 0.0 <= out["score"] <= 1.0
    assert out["score_band"] in ("low", "medium", "high", "critical")
    assert set(out["score_subscores"]) == {
        "complexity_burden",
        "maintainability_burden",
        "churn_burden",
        "smell_burden",
        "similarity_burden",
    }


def test_similarity_unavailable_zeros_similarity_burden_and_redistributes():
    cfg = copy.deepcopy(DEFAULTS)
    rec = _neutral_record()
    rec["similarity_score"] = 100.0
    rec["match_count"] = 5.0
    with_sim = compute_score(rec, cfg, similarity_available=True)
    without = compute_score(rec, cfg, similarity_available=False)
    assert without["score_subscores"]["similarity_burden"] == pytest.approx(0.0)
    assert with_sim["score"] != without["score"]


def test_score_aggregation_disabled_leaves_score_unchanged():
    cfg = copy.deepcopy(DEFAULTS)
    cfg["score_aggregation"] = {"enabled": False}
    rec = _neutral_record()
    rec["score"] = 123.45
    out = compute_score(rec, cfg, similarity_available=True)
    assert out["score"] == 123.45


def test_effective_score_aggregation_merges_user_partial():
    cfg = {"score_aggregation": {"enabled": True, "band_edges": [0.25, 0.5, 0.75]}}
    eff = effective_score_aggregation(cfg)
    assert eff["band_edges"] == [0.25, 0.5, 0.75]
    assert "complexity_weights" in eff


def test_score_aggregation_enabled_respects_false():
    assert score_aggregation_enabled({"score_aggregation": {"enabled": False}}) is False


def test_validate_rejects_final_weights_not_summing_to_one():
    cfg = copy.deepcopy(DEFAULTS)
    cfg["score_aggregation"]["final_weights"]["complexity_burden"] = 0.5
    with pytest.raises(ValueError, match="sum to 1.0"):
        validate_score_aggregation(cfg)


def test_validate_rejects_bad_band_edge_order():
    cfg = copy.deepcopy(DEFAULTS)
    cfg["score_aggregation"]["band_edges"] = [0.6, 0.3, 0.8]
    with pytest.raises(ValueError, match="strictly increasing"):
        validate_score_aggregation(cfg)


def test_high_score_maps_to_high_or_critical_band():
    cfg = copy.deepcopy(DEFAULTS)
    rec = _neutral_record()
    rec["cyclomatic"] = 25
    rec["halstead"] = 500
    rec["maintainability"] = 15
    rec["churn"] = 100
    rec["churn_per_sloc"] = 1.0
    rec["decayed_churn"] = 100.0
    rec["decayed_churn_per_sloc"] = 1.0
    rec["smell_count"] = 15.0
    rec["smell_severity"] = 1.0
    rec["similarity_score"] = 100.0
    rec["match_count"] = 10.0
    out = compute_score(rec, cfg, similarity_available=True)
    assert out["score_band"] in ("high", "critical")
    assert out["score"] >= 0.60
