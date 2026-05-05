"""Thread-safe MCP tool call statistics for the dashboard."""
from __future__ import annotations

import copy
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class ToolStats:
    num_calls: int = 0
    num_errors: int = 0
    total_duration_ms: float = 0.0
    last_called_at: str | None = None

    @property
    def avg_duration_ms(self) -> float:
        if self.num_calls <= 0:
            return 0.0
        return self.total_duration_ms / self.num_calls


@dataclass
class StatsCollector:
    """Tracks per-tool invocation metrics; safe under concurrent MCP tool calls."""

    _stats: dict[str, ToolStats] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record_call(self, tool_name: str, duration_ms: float, *, error: bool = False) -> None:
        name = str(tool_name)
        if not name:
            raise ValueError("tool_name must be non-empty")
        if duration_ms < 0:
            raise ValueError(f"duration_ms must be non-negative; got {duration_ms}")
        with self._lock:
            s = self._stats.setdefault(name, ToolStats())
            s.num_calls += 1
            s.total_duration_ms += float(duration_ms)
            s.last_called_at = datetime.now(timezone.utc).isoformat()
            if error:
                s.num_errors += 1

    def get_snapshot(self) -> dict[str, dict[str, int | float | str | None]]:
        """Deep copy of all tool stats (safe to JSON-serialize)."""
        with self._lock:
            return copy.deepcopy(
                {
                    name: {
                        "num_calls": s.num_calls,
                        "num_errors": s.num_errors,
                        "avg_duration_ms": round(s.avg_duration_ms, 2),
                        "total_duration_ms": round(s.total_duration_ms, 2),
                        "last_called_at": s.last_called_at,
                    }
                    for name, s in self._stats.items()
                }
            )

    def clear(self) -> None:
        with self._lock:
            self._stats.clear()
