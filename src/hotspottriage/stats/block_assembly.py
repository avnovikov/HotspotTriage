"""Pass 3: assemble per-block metric dicts and cache metadata."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hotspottriage import blocks as _blocks
from hotspottriage import complexity as _complexity
from hotspottriage.config import DEFAULTS as _DEFAULTS

from hotspottriage.stats.block_context import BlockAnalysisContext
from hotspottriage.stats.block_options import BlockAssemblyInputs
from hotspottriage.stats.metrics import decayed_value, ratio


@dataclass(frozen=True, slots=True)
class _PerBlockChurnFrame:
    rel: str
    block: _blocks.Block
    age_seconds: int
    min_sloc: int
    decay_half_life: int | None


def _block_churn_metrics(
    m: dict[str, Any],
    churns: dict[tuple[str, int, int], int],
    frame: _PerBlockChurnFrame,
) -> None:
    """Populate churn / decayed-churn fields on a block metrics dict."""
    b = frame.block
    m["churn"] = churns.get((frame.rel, b.start, b.end), 0)
    m["churn_per_sloc"] = ratio(int(m["churn"]), int(m["sloc"]), min_sloc_for_ratio=frame.min_sloc)
    m["decayed_churn"] = (
        decayed_value(m["churn"], frame.age_seconds, frame.decay_half_life)
        if frame.decay_half_life
        else m["churn"]
    )
    m["decayed_churn_per_sloc"] = ratio(
        m["decayed_churn"], int(m["sloc"]), min_sloc_for_ratio=frame.min_sloc
    )


@dataclass(frozen=True, slots=True)
class _BlockSmellAssemblyInput:
    file_path: Path
    block: _blocks.Block
    file_smells_for_rel: list[dict[str, Any]]
    merged_config: dict[str, Any]
    func_by_name: dict[str, Any]
    smell_res_cfg: dict[str, Any]


def _block_smell_metrics(m: dict[str, Any], smell: _BlockSmellAssemblyInput) -> None:
    """Collect per-block smell findings and populate count / severity / summary."""
    from hotspottriage import smell as _smell

    b = smell.block
    block_findings = [
        s for s in smell.file_smells_for_rel if _smell.finding_applies_to_block(s, b)
    ]
    tw = _smell.maybe_trivial_wrapper_block_finding(
        file_path=str(smell.file_path),
        block=b,
        metrics=m,
        pylint_block_findings=block_findings,
        merged_config=smell.merged_config,
        func_node=smell.func_by_name.get(b.name),
    )
    if tw is not None:
        tw["severity"] = _smell.resolve_smell_severity(tw, smell.smell_res_cfg)
        block_findings.append(tw)

    n = len(block_findings)
    m["smell_count"] = float(n)
    m["smell_severity"] = (
        sum(float(s.get("severity", 0.0)) for s in block_findings) / max(1, n)
        if block_findings
        else 0.0
    )
    m["smells"] = _smell.summarize_smells(block_findings)


def assemble_block_metrics(
    ctx: BlockAnalysisContext,
    inputs: BlockAssemblyInputs,
) -> tuple[list[tuple[str, _blocks.Block, dict[str, Any]]], list[dict[str, str | int]]]:
    """Pass 3: assemble block metric dicts with cache metadata."""
    from hotspottriage import smell as _smell

    file_metrics = inputs.file_metrics
    file_blocks = inputs.file_blocks
    file_sources = inputs.file_sources
    file_smells = inputs.file_smells
    churns = inputs.churns

    rows: list[tuple[str, _blocks.Block, dict[str, Any]]] = []
    row_cache_meta: list[dict[str, str | int]] = []
    smell_cfg = ctx.merged_config if ctx.merged_config else _DEFAULTS
    min_sloc = int(
        (ctx.merged_config or {}).get("min_sloc_for_ratio", _DEFAULTS["min_sloc_for_ratio"])
    )

    for rel in ctx.files:
        if rel not in file_blocks:
            continue
        src = file_sources[rel]
        file_mi = file_metrics[rel]["maintainability"]
        age_seconds = ctx.current_time - ctx.timestamps.get(rel, ctx.current_time)
        func_by_name = _smell.function_defs_by_qualname(src)
        smell_res_cfg = _smell.smell_resolution_cfg(ctx.merged_config)

        for b in file_blocks[rel]:
            snippet = _complexity.slice_block(src, b.start, b.end)
            m: dict[str, Any] = dict(_complexity.compute_for_source(snippet))
            m["maintainability"] = file_mi

            churn_frame = _PerBlockChurnFrame(
                rel=rel,
                block=b,
                age_seconds=age_seconds,
                min_sloc=min_sloc,
                decay_half_life=ctx.decay_half_life,
            )
            _block_churn_metrics(m, churns, churn_frame)

            smell_in = _BlockSmellAssemblyInput(
                file_path=ctx.repo / rel,
                block=b,
                file_smells_for_rel=file_smells.get(rel, []),
                merged_config=smell_cfg,
                func_by_name=func_by_name,
                smell_res_cfg=smell_res_cfg,
            )
            _block_smell_metrics(m, smell_in)

            rows.append((rel, b, m))
            row_cache_meta.append({
                "_blob_sha": ctx.blob_shas[rel],
                "_start": b.start,
                "_end": b.end,
            })

    return rows, row_cache_meta
