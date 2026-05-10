"""Pass 2: parallel per-block churn (``git log -L``)."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from hotspottriage import block_churn as _block_churn

from hotspottriage.stats.block_context import BlockAnalysisContext


def compute_block_churns(
    ctx: BlockAnalysisContext,
    requests: list[tuple[str, str, int, int]],
    since: str | None,
    until: str | None,
    workers: int | None,
    progress_callback: Callable[[str, int, int], None] | None,
) -> dict[tuple[str, int, int], int]:
    """Pass 2: parallel git log -L for all blocks (cached)."""

    def _churn_progress(done: int, total: int) -> None:
        if progress_callback:
            progress_callback("Block churn (git log -L)", done, total)

    return _block_churn.compute_many(
        ctx.repo,
        requests,
        since,
        until,
        previous_rows=ctx.previous_rows,
        workers=workers,
        on_progress=_churn_progress if progress_callback else None,
    )
