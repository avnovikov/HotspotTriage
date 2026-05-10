"""Pass 2: parallel per-block churn (``git log -L``)."""
from __future__ import annotations

from hotspottriage import block_churn as _block_churn

from hotspottriage.stats.block_context import BlockAnalysisContext
from hotspottriage.stats.block_options import ChurnComputeSpec


def compute_block_churns(
    ctx: BlockAnalysisContext,
    requests: list[tuple[str, str, int, int]],
    spec: ChurnComputeSpec,
) -> dict[tuple[str, int, int], int]:
    """Pass 2: parallel git log -L for all blocks (cached)."""

    def _churn_progress(done: int, total: int) -> None:
        if spec.progress_callback:
            spec.progress_callback("Block churn (git log -L)", done, total)

    return _block_churn.compute_many(
        ctx.repo,
        requests,
        spec.since,
        spec.until,
        previous_rows=ctx.previous_rows,
        workers=spec.workers,
        on_progress=_churn_progress if spec.progress_callback else None,
    )
