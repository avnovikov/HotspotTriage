"""Serialize block ``Statistic`` rows for MCP analyze JSON output."""

from __future__ import annotations

from typing import Any

from hotspottriage import output as ht_output
from hotspottriage import stats
from hotspottriage.mcp.compact_score_rows import compact_score_rows


def block_analysis_results_as_dicts(
    results: list[stats.Statistic],
    *,
    compact: bool,
    merged_config: dict[str, Any],
) -> list[dict[str, Any]]:
    """Limited block rows as compact triage dicts or full metric dicts."""
    if compact:
        return compact_score_rows(
            results, granularity="block", merged_config=merged_config
        )
    return [ht_output.statistic_to_output_dict(row, merged_config) for row in results]
