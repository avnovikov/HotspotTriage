"""Tests for hotspottriage.dashboard.server."""
from __future__ import annotations

import asyncio
import logging
import socket

from fastapi.testclient import TestClient

from hotspottriage.dashboard.log_handler import MemoryLogHandler
from hotspottriage.dashboard.server import DashboardServer, _find_free_port
from hotspottriage.dashboard.stats import StatsCollector


def _server() -> DashboardServer:
    stats = StatsCollector()
    logs = MemoryLogHandler(max_records=100)
    return DashboardServer(
        config={"dashboard": {"enabled": True}},
        stats=stats,
        log_handler=logs,
        host="127.0.0.1",
        base_port=9200,
        open_on_start=False,
    )


def test_find_free_port_returns_in_range():
    port = _find_free_port("127.0.0.1", 9300, span=3)
    assert 9300 <= port <= 9302


def test_find_free_port_raises_when_range_busy():
    sockets: list[socket.socket] = []
    try:
        for p in (9400, 9401):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", p))
            s.listen(1)
            sockets.append(s)
        try:
            _find_free_port("127.0.0.1", 9400, span=2)
            assert False, "expected OSError when no port is available"
        except OSError:
            pass
    finally:
        for s in sockets:
            s.close()


def test_dashboard_endpoints_health_config_stats_logs():
    srv = _server()
    # Seed data
    srv._stats.record_call("analyze", 10.0)
    log_record = logging.LogRecord("t", logging.INFO, "", 0, "hello", (), None)
    srv._log_handler.emit(log_record)
    client = TestClient(srv.app)

    h = client.get("/api/health")
    assert h.status_code == 200
    assert h.json()["status"] == "alive"

    c = client.get("/api/config")
    assert c.status_code == 200
    assert c.json()["dashboard"]["enabled"] is True

    st = client.get("/api/stats")
    assert st.status_code == 200
    assert st.json()["analyze"]["num_calls"] == 1

    lg = client.get("/api/logs?from_idx=0")
    assert lg.status_code == 200
    assert lg.json()["messages"]
    assert lg.json()["max_idx"] >= 1

    clr = client.post("/api/stats/clear")
    assert clr.status_code == 200
    assert clr.json()["status"] == "cleared"
    assert client.get("/api/stats").json() == {}


def test_stream_endpoints_exist():
    srv = _server()
    client = TestClient(srv.app)
    assert client.get("/dashboard/").status_code == 200
    paths = {r.path for r in srv.app.router.routes}
    assert "/api/logs/stream" in paths
    assert "/api/stats/stream" in paths


def test_start_runs_daemon_thread(monkeypatch):
    srv = _server()

    async def _fake_serve(self) -> bool:
        return True

    monkeypatch.setattr("uvicorn.Server.serve", _fake_serve)
    srv.start()
    assert srv._thread is not None
    assert srv._thread.daemon is True
    srv._thread.join(timeout=1.0)
