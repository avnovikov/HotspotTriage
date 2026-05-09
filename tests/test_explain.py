"""Tests for score narrative helpers (issue #103)."""
from __future__ import annotations

from hotspottriage.explain import (
    build_score_explanation,
    explain_score,
    score_driver_from_subscores,
)
from hotspottriage.statistic_row import Statistic


def _block_stat(**kwargs) -> Statistic:
    base = dict(
        path="src/stats.py::build_block_stats",
        sloc=40,
        normalized_sloc=0.5,
        cyclomatic=18,
        halstead=842,
        maintainability=12,
        churn=34,
        churn_per_sloc=0.85,
        decayed_churn=30.0,
        decayed_churn_per_sloc=0.75,
        smell_count=4,
        smell_severity=2.1,
        smell_burden=0.4,
        smells={},
        similarity_score=18.0,
        similarity_band="medium",
        match_count=2,
        score=0.87,
        score_band="high",
        score_subscores={
            "complexity_burden": 0.91,
            "churn_burden": 0.74,
            "maintainability_burden": 0.55,
            "smell_burden": 0.63,
            "similarity_burden": 0.22,
        },
    )
    base.update(kwargs)
    return Statistic(**base)


def test_score_driver_from_subscores_picks_max():
    s = _block_stat()
    assert score_driver_from_subscores(s.score_subscores) == "complexity"


def test_build_score_explanation_orders_by_burden():
    s = _block_stat()
    expl = build_score_explanation(s)
    drivers = [x["driver"] for x in expl]
    assert drivers[0] == "complexity"
    assert expl[0]["raw"]["cyclomatic"] == 18
    assert "smells" in drivers


def test_explain_score_includes_header_and_recommended_action():
    s = _block_stat()
    text = explain_score(s, recommended_action="Assign senior reviewer")
    assert "HIGH RISK" in text
    assert "src/stats.py::build_block_stats" in text
    assert "Primary driver:" in text
    assert "Assign senior reviewer" in text


def test_explain_score_empty_when_no_subscores():
    s = _block_stat(score_subscores={})
    assert explain_score(s) == ""


def test_explain_score_falls_back_to_human_review():
    s = _block_stat()
    assert "Human review" in explain_score(s)

