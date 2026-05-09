"""Tests for score narrative helpers (issue #103)."""
from __future__ import annotations

import copy

from hotspottriage.config import DEFAULTS
from hotspottriage.explain import (
    build_score_explanation,
    explain_score,
    score_driver_from_subscores,
)
from hotspottriage.score import (
    final_weight_multipliers_for_burdens,
    normalized_block_inputs,
)
from hotspottriage.statistic_row import Statistic


def _metric_rec_from_stat_fields(d: dict) -> dict[str, float]:
    return {
        "normalized_sloc": float(d.get("normalized_sloc", 0.0)),
        "cyclomatic": float(d.get("cyclomatic", 0)),
        "halstead": float(d.get("halstead", 0)),
        "maintainability": float(d.get("maintainability", 0)),
        "churn": float(d.get("churn", 0)),
        "churn_per_sloc": float(d.get("churn_per_sloc", 0.0)),
        "decayed_churn": float(d.get("decayed_churn", 0.0)),
        "decayed_churn_per_sloc": float(d.get("decayed_churn_per_sloc", 0.0)),
        "smell_count": float(d.get("smell_count", 0)),
        "smell_severity": float(d.get("smell_severity", 0.0)),
        "similarity_score": float(d.get("similarity_score", 0.0)),
        "match_count": float(d.get("match_count", 0)),
    }


def _block_stat(**kwargs) -> Statistic:
    cfg = copy.deepcopy(DEFAULTS)
    fw = final_weight_multipliers_for_burdens(cfg, similarity_available=True)
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
        score_final_weights=fw,
    )
    base.update(kwargs)
    sni = base.pop("score_norm_inputs", None)
    if sni is None and base.get("score_subscores"):
        rec = _metric_rec_from_stat_fields(base)
        sni = normalized_block_inputs(rec, cfg, similarity_available=True)
    if sni is not None:
        base["score_norm_inputs"] = sni
    return Statistic(**base)


def test_score_driver_from_subscores_picks_max():
    s = _block_stat()
    assert score_driver_from_subscores(s.score_subscores) == "complexity"


def test_weighted_score_driver_can_differ_from_unweighted_max():
    s = _block_stat(
        score_subscores={
            "complexity_burden": 0.95,
            "churn_burden": 0.50,
            "maintainability_burden": 0.90,
            "smell_burden": 0.0,
            "similarity_burden": 0.0,
        },
        score_final_weights=None,
    )
    fw = {
        "complexity_burden": 0.05,
        "churn_burden": 0.50,
        "maintainability_burden": 0.10,
        "smell_burden": 0.15,
        "similarity_burden": 0.20,
    }
    assert score_driver_from_subscores(s.score_subscores, final_weights=fw) == "churn"
    assert score_driver_from_subscores(s.score_subscores) == "complexity"


def test_build_score_explanation_orders_by_burden():
    s = _block_stat()
    expl = build_score_explanation(s)
    drivers = [x["driver"] for x in expl]
    assert drivers[0] == "complexity"
    assert expl[0]["raw"]["cyclomatic"] == 18
    assert "normalized" in expl[0]
    assert 0.0 <= float(expl[0]["normalized"]["cyclomatic"]) <= 1.0
    assert "score_contribution" in expl[0]
    assert "smells" in drivers


def test_explain_score_includes_header_and_recommended_action():
    s = _block_stat()
    text = explain_score(s, recommended_action="Assign senior reviewer")
    assert "HIGH RISK" in text
    assert "src/stats.py::build_block_stats" in text
    assert "Primary driver:" in text
    assert "score contribution" in text
    assert "n_churn=" in text or "n_cyclomatic=" in text
    assert "Assign senior reviewer" in text


def test_explain_score_empty_when_no_subscores():
    s = _block_stat(score_subscores={})
    assert explain_score(s) == ""


def test_explain_score_falls_back_to_human_review():
    s = _block_stat()
    assert "Human review" in explain_score(s)
