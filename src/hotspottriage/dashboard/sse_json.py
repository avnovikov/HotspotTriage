"""SSE helpers emitting JSON snapshots on an interval."""
from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator, Callable


async def sse_json_every(
    interval_s: float,
    build_payload: Callable[[], Any],
) -> AsyncGenerator[str, None]:
    """SSE stream: emit JSON snapshots on a fixed interval."""
    while True:
        yield "data: " + json.dumps(build_payload()) + "\n\n"
        await asyncio.sleep(interval_s)
