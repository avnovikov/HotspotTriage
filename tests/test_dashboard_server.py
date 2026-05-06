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


def test_generate_cache_endpoint(monkeypatch):
    srv = _server()
    client = TestClient(srv.app)

    def _fake_generate_full_cache(
        target: str, filter: str | None, score_metrics: str, verbose: bool
    ) -> dict:
        assert target == "../LexVox"
        assert filter is None
        assert score_metrics == "churn_per_sloc,cyclomatic"
        assert verbose is False
        return {
            "metadata": {"blocks_cached": 10, "classes_indexed": 5},
            "cache_status": {"entries": 10},
            "blocks": {"count": 10},
        }

    monkeypatch.setattr(
        "hotspottriage.cache_generator.generate_full_cache",
        _fake_generate_full_cache,
    )
    start = client.post("/api/cache/generate", json={"target": "../LexVox"})
    assert start.status_code == 200
    job_id = start.json()["job_id"]
    for _ in range(10):
        status = client.get(f"/api/cache/jobs/{job_id}")
        assert status.status_code == 200
        data = status.json()
        if data["status"] != "running":
            break
    assert data["status"] == "done"
    assert data["result"]["metadata"]["blocks_cached"] == 10


def test_generate_cache_requires_target():
    srv = _server()
    client = TestClient(srv.app)
    resp = client.post("/api/cache/generate", json={})
    assert resp.status_code == 400


def test_cache_status_endpoint(monkeypatch, tmp_path):
    srv = _server()
    client = TestClient(srv.app)
    repo = tmp_path / "r"
    repo.mkdir()
    cache_dir = repo / ".hotspottriage" / "cache"
    cache_dir.mkdir(parents=True)
    (cache_dir / "blocks.pkl").write_bytes(b"abc")

    class _FakeCache:
        def __init__(self, _repo):
            pass

        def get_metadata(self):
            return {"entry_count": 7}

    monkeypatch.setattr("hotspottriage.dashboard.server._cache.Cache", _FakeCache)
    resp = client.post("/api/cache/status", json={"target": str(repo)})
    assert resp.status_code == 200
    data = resp.json()
    assert data["exists"] is True
    assert data["entries"] == 7


def test_cache_context_persists_locally(tmp_path):
    srv = _server()
    srv._state_file = tmp_path / ".hotspottriage" / "dashboard_state.json"
    client = TestClient(srv.app)
    set_resp = client.post(
        "/api/cache/context",
        json={
            "target": "../LexVox",
            "filter": "src/**",
            "score_metrics": "cyclomatic,churn",
        },
    )
    assert set_resp.status_code == 200
    get_resp = client.get("/api/cache/context")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["last_target"] == "../LexVox"
    assert data["last_filter"] == "src/**"
    assert data["last_score_metrics"] == "cyclomatic,churn"
    assert data["recent_targets"][0] == "../LexVox"


def test_generate_cache_job_not_found():
    srv = _server()
    client = TestClient(srv.app)
    resp = client.get("/api/cache/jobs/missing")
    assert resp.status_code == 404


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
