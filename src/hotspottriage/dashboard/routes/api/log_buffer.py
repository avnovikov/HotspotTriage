"""Dashboard API: in-memory log ring buffer and SSE stream."""
from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from hotspottriage.dashboard.log_handler import MemoryLogHandler


def register_log_buffer_routes(
    router: APIRouter,
    *,
    log_handler: MemoryLogHandler,
) -> None:
    """Register ``/logs`` and ``/logs/stream``."""

    @router.get("/logs")
    def get_logs(from_idx: int = 0) -> dict[str, Any]:
        lm = log_handler.get_log_messages(from_idx=from_idx)
        return {"messages": lm.messages, "max_idx": lm.max_idx}

    async def _log_sse() -> AsyncGenerator[str, None]:
        last_idx = 0
        while True:
            result = log_handler.get_log_messages(from_idx=last_idx)
            if result.messages:
                for msg in result.messages:
                    yield "data: " + json.dumps(msg) + "\n\n"
                last_idx = result.max_idx
            await asyncio.sleep(1.0)

    @router.get("/logs/stream")
    def log_stream() -> StreamingResponse:
        return StreamingResponse(_log_sse(), media_type="text/event-stream")
