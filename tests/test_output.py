"""Tests for hotspottriage.output normalization wiring."""
from __future__ import annotations

import json

import pytest

from hotspottriage.config import DEFAULTS
from hotspottriage.output import (
    display_headers,
    proposed_model_for_band,
    render_json,
    statistic_to_output_dict,
)
from hotspottriage.stats import Statistic


def _minimal_stat(**kwargs) -> Statistic:
    base = dict(
        path="x.py",
        sloc=10,
        normalized_sloc=0.0,
        cyclomatic=3,
        halstead=50,
        maintainability=50,
        churn=5,
        churn_per_sloc=0.5,
        decayed_churn=5.0,
        decayed_churn_per_sloc=0.5,
        smell_count=0,
        smell_severity=0.0,
        smell_burden=0.0,
        smells={},
        similarity_score=0.0,
        similarity_band="n/a",
        match_count=0,
        score=1.0,
    )
    base.update(kwargs)
    return Statistic(**base)


def test_display_headers_appends_norm_columns():
    hdr = display_headers(DEFAULTS)
    assert hdr[:3] == ("path", "sloc", "normalized_sloc")
    assert "norm_cyclomatic" in hdr
    assert hdr.index("norm_cyclomatic") > hdr.index("score")


def test_statistic_to_output_dict_adds_norm_fields():
    s = _minimal_stat()
    d = statistic_to_output_dict(s, DEFAULTS)
    assert "norm_cyclomatic" in d
    assert 0.0 <= float(d["norm_cyclomatic"]) <= 1.0


def test_render_json_includes_norm_keys():
    s = _minimal_stat()
    out = render_json([s], merged_config=DEFAULTS)
    row = json.loads(out)[0]
    assert "norm_halstead" in row


def test_statistic_to_output_dict_without_config_skips_norm():
    s = _minimal_stat()
    d = statistic_to_output_dict(s, None)
    assert "norm_cyclomatic" not in d


def test_statistic_to_output_dict_empty_normalization_skips_norm():
    s = _minimal_stat()
    d = statistic_to_output_dict(s, {"metric_normalization": {}})
    assert "norm_cyclomatic" not in d


def test_norm_similarity_score_is_raw_over_100():
    s = _minimal_stat(similarity_score=50.0)
    d = statistic_to_output_dict(s, DEFAULTS)
    assert d["norm_similarity_score"] == pytest.approx(0.5)


def test_proposed_model_for_band_is_case_insensitive_for_lookup():
    cfg = {
        **DEFAULTS,
        "proposed_models": {
            "low": "L",
            "medium": "M",
            "high": "H",
            "critical": "C",
        },
    }
    assert proposed_model_for_band("high", cfg) == "H"
    assert proposed_model_for_band("High", cfg) == "H"


def test_statistic_to_output_dict_adds_proposed_model_and_rationale_keys():
    s = _minimal_stat()
    d = statistic_to_output_dict(s, DEFAULTS)
    assert "proposed_model" in d and isinstance(d["proposed_model"], str)
    assert "rationale" in d and isinstance(d["rationale"], str)
