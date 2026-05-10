"""Dashboard API: StatsCollector snapshot, clear, and SSE stream."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from hotspottriage.dashboard.stats import StatsCollector
from hotspottriage.dashboard.sse_json import sse_json_every


def register_collector_stats_routes(
    router: APIRouter,
    *,
    stats_collector: StatsCollector,
) -> None:
    """Register ``/stats``, ``/stats/clear``, ``/stats/stream``."""

    @router.get("/stats")
    def get_stats() -> dict[str, Any]:
        return stats_collector.get_snapshot()

    @router.post("/stats/clear")
    def clear_stats() -> dict[str, str]:
        stats_collector.clear()
        return {"status": "cleared"}

    @router.get("/stats/stream")
    def stats_stream() -> StreamingResponse:
        return StreamingResponse(
            sse_json_every(5.0, stats_collector.get_snapshot),
            media_type="text/event-stream",
        )
