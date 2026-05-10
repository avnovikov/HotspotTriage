"""Pass 3: assemble per-block metric dicts and cache metadata."""
from __future__ import annotations

from typing import Any

from hotspottriage import blocks as _blocks
from hotspottriage import complexity as _complexity
from hotspottriage.config import DEFAULTS as _DEFAULTS

from hotspottriage.stats.block_context import BlockAnalysisContext
from hotspottriage.stats.metrics import decayed_value, ratio


def assemble_block_metrics(
    ctx: BlockAnalysisContext,
    file_metrics: dict[str, dict[str, int]],
    file_blocks: dict[str, list[_blocks.Block]],
    file_sources: dict[str, str],
    file_smells: dict[str, list[dict[str, Any]]],
    churns: dict[tuple[str, int, int], int],
    decay_half_life: int | None,
) -> tuple[list[tuple[str, _blocks.Block, dict[str, Any]]], list[dict[str, str | int]]]:
    """Pass 3: assemble block metric dicts with cache metadata."""
    from hotspottriage import smell as _smell

    rows: list[tuple[str, _blocks.Block, dict[str, Any]]] = []
    row_cache_meta: list[dict[str, str | int]] = []

    for rel in ctx.files:
        if rel not in file_blocks:
            continue
        src = file_sources[rel]
        file_mi = file_metrics[rel]["maintainability"]
        age_seconds = ctx.current_time - ctx.timestamps.get(rel, ctx.current_time)
        min_sloc = int(
            (ctx.merged_config or {}).get(
                "min_sloc_for_ratio", _DEFAULTS["min_sloc_for_ratio"]
            )
        )
        func_by_name = _smell.function_defs_by_qualname(src)
        smell_res_cfg = _smell.smell_resolution_cfg(ctx.merged_config)

        for b in file_blocks[rel]:
            snippet = _complexity.slice_block(src, b.start, b.end)
            m: dict[str, Any] = dict(_complexity.compute_for_source(snippet))
            m["maintainability"] = file_mi
            m["churn"] = churns.get((rel, b.start, b.end), 0)
            m["churn_per_sloc"] = ratio(
                int(m["churn"]), int(m["sloc"]), min_sloc_for_ratio=min_sloc
            )
            m["decayed_churn"] = (
                decayed_value(m["churn"], age_seconds, decay_half_life)
                if decay_half_life
                else m["churn"]
            )
            m["decayed_churn_per_sloc"] = ratio(
                m["decayed_churn"], int(m["sloc"]), min_sloc_for_ratio=min_sloc
            )

            block_raw = [
                s for s in file_smells.get(rel, []) if _smell.finding_applies_to_block(s, b)
            ]
            merged_for_smell = ctx.merged_config if ctx.merged_config else _DEFAULTS
            tw = _smell.maybe_trivial_wrapper_block_finding(
                file_path=str(ctx.repo / rel),
                block=b,
                metrics=m,
                pylint_block_findings=block_raw,
                merged_config=merged_for_smell,
                func_node=func_by_name.get(b.name),
            )
            if tw is not None:
                tw["severity"] = _smell.resolve_smell_severity(tw, smell_res_cfg)
                block_raw.append(tw)
            block_summary = _smell.summarize_smells(block_raw)
            n_blk = len(block_raw)
            m["smell_count"] = float(n_blk)
            m["smell_severity"] = (
                sum(float(s.get("severity", 0.0)) for s in block_raw) / max(1, n_blk)
                if block_raw
                else 0.0
            )
            m["smells"] = block_summary

            rows.append((rel, b, m))
            row_cache_meta.append({
                "_blob_sha": ctx.blob_shas[rel],
                "_start": b.start,
                "_end": b.end,
            })

    return rows, row_cache_meta
