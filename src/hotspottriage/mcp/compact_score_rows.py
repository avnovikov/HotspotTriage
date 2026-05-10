"""Compact MCP ``analyze`` result rows (triage fields only)."""

from __future__ import annotations

from typing import Any

from hotspottriage import explain as ht_explain
from hotspottriage import output as ht_output
from hotspottriage import stats


def compact_score_rows(
    rows: list[stats.Statistic],
    *,
    granularity: str,
    merged_config: dict[str, Any],
) -> list[dict[str, Any]]:
    """One dict per row: file, symbol, score, band, model, driver, short rationale."""
    out: list[dict[str, Any]] = []
    for r in rows:
        p = r.path
        if granularity == "block" and "::" in p:
            file_path, fn = p.split("::", 1)
        else:
            file_path, fn = p, p
        score_band = str(r.score_band)
        out.append(
            {
                "file": file_path,
                "function": fn,
                "score": float(r.score),
                "risk_band": score_band,
                "proposed_model": ht_output.proposed_model_for_band(
                    score_band, merged_config
                ),
                "score_driver": r.score_driver,
                "rationale": ht_explain.compact_agent_rationale(
                    r, final_weights=r.score_final_weights
                ),
            }
        )
    return out
