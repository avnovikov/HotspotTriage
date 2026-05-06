"""In-process dashboard support (stats, logs, HTTP server)."""

from hotspottriage.dashboard.log_handler import LogMessages, MemoryLogHandler
from hotspottriage.dashboard.server import DashboardServer
from hotspottriage.dashboard.stats import StatsCollector, ToolStats

__all__ = (
    "DashboardServer",
    "LogMessages",
    "MemoryLogHandler",
    "StatsCollector",
    "ToolStats",
)
