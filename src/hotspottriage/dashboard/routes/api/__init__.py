"""Modular FastAPI ``/api`` routes for the HotspotTriage dashboard."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from hotspottriage.dashboard.routes.api.block_metrics import register_block_metric_routes
from hotspottriage.dashboard.routes.api.cache import register_cache_routes
from hotspottriage.dashboard.routes.api.collector_stats import register_collector_stats_routes
from hotspottriage.dashboard.routes.api.health_config import register_health_and_config_routes
from hotspottriage.dashboard.routes.api.log_buffer import register_log_buffer_routes


def build_dashboard_api_router(dash: Any) -> APIRouter:
    """Return an ``APIRouter`` with prefix ``/api`` wired to *dash* (:class:`DashboardServer`)."""
    router = APIRouter(prefix="/api")
    register_health_and_config_routes(router, dash)
    register_block_metric_routes(router, dash)
    register_cache_routes(router, dash)
    register_collector_stats_routes(router, stats_collector=dash._stats)
    register_log_buffer_routes(router, log_handler=dash._log_handler)
    return router
