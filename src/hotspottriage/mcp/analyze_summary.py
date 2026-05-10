"""Aggregate block metrics for MCP ``include_summary``."""

from __future__ import annotations

from typing import Any

from hotspottriage import stats
from hotspottriage.mcp.block_row_utils import non_synthetic_block_rows


def build_mcp_analyze_summary(rows: list[stats.Statistic]) -> dict[str, Any]:
    """Aggregate metrics over the full (pre-``limit``) block list."""
    blocks = non_synthetic_block_rows(rows)
    n = len(blocks)
    if n == 0:
        return {
            "block_count": 0,
            "high_risk_count": 0,
            "critical_risk_count": 0,
            "sum_cyclomatic": 0,
            "sum_sloc": 0,
            "max_cyclomatic": None,
            "max_score": None,
            "mean_score": 0.0,
        }
    high_risk_count = sum(1 for r in blocks if str(r.score_band).lower() == "high")
    critical_risk_count = sum(
        1 for r in blocks if str(r.score_band).lower() == "critical"
    )
    sum_cyclomatic = sum(int(r.cyclomatic) for r in blocks)
    sum_sloc = sum(int(r.sloc) for r in blocks)
    max_cyc = max(blocks, key=lambda r: int(r.cyclomatic))
    max_sc = max(blocks, key=lambda r: float(r.score))
    total_score = sum(float(r.score) for r in blocks)
    return {
        "block_count": n,
        "high_risk_count": high_risk_count,
        "critical_risk_count": critical_risk_count,
        "sum_cyclomatic": sum_cyclomatic,
        "sum_sloc": sum_sloc,
        "max_cyclomatic": {"path": max_cyc.path, "value": int(max_cyc.cyclomatic)},
        "max_score": {"path": max_sc.path, "value": round(float(max_sc.score), 4)},
        "mean_score": round(total_score / n, 4),
    }
