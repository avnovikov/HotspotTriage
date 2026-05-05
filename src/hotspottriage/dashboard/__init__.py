"""In-process dashboard support (stats, logs, HTTP server)."""

from hotspottriage.dashboard.stats import StatsCollector, ToolStats

__all__ = ("StatsCollector", "ToolStats")
