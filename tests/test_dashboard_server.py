"""Tests for hotspottriage.dashboard.server."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
import socket

import pytest
from fastapi.testclient import TestClient

from hotspottriage import config as _project_config
from hotspottriage.dashboard.log_handler import MemoryLogHandler
from hotspottriage.dashboard.server import DashboardServer, _find_free_port, _slim_cache_job_result
from hotspottriage.dashboard.stats import StatsCollector


def _server(
    *,
    config_patch_path=None,
    config_snapshot: dict | None = None,
) -> DashboardServer:
    stats = StatsCollector()
    logs = MemoryLogHandler(max_records=100)
    snap = config_snapshot or _project_config.to_dashboard_snapshot(
        dict(_project_config.DEFAULTS)
    )
    return DashboardServer(
        config=snap,
        stats=stats,
        log_handler=logs,
        host="127.0.0.1",
        base_port=9200,
        open_on_start=False,
        config_patch_path=config_patch_path,
    )


def _default_score_metrics_csv() -> str:
    metrics = _project_config.DEFAULTS.get("score_metrics") or []
    return ",".join(str(m) for m in metrics)


def _high_raw_block_row(path: str = "x.py::f") -> dict:
    return {
        "path": path,
        "sloc": 85,
        "normalized_sloc": 2.5,
        "cyclomatic": 24,
        "halstead": 619,
        "maintainability": 20,
        "churn": 104,
        "churn_per_sloc": 1.2,
        "decayed_churn": 100.0,
        "decayed_churn_per_sloc": 1.1,
        "smell_count": 10,
        "smell_severity": 1.0,
        "smell_burden": 1.0,
        "smells": {},
        "similarity_score": 0.0,
        "similarity_band": "off",
        "match_count": 0,
    }


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
        target: str,
        filter: str | None,
        score_metrics: str,
        verbose: bool,
        progress_callback=None,
        config_overrides=None,
    ) -> dict:
        assert target == str((Path.cwd() / "../LexVox").resolve())
        assert filter is None
        assert score_metrics == _default_score_metrics_csv()
        assert verbose is False
        assert isinstance(config_overrides, dict)
        assert "score_aggregation" in config_overrides
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


def test_generate_cache_passes_composed_filter_from_include_exclude(monkeypatch):
    srv = _server()
    client = TestClient(srv.app)
    captured: dict[str, str | None] = {}

    def _fake_generate_full_cache(
        target: str,
        filter: str | None,
        score_metrics: str,
        verbose: bool,
        progress_callback=None,
        config_overrides=None,
    ) -> dict:
        captured["filter"] = filter
        return {"metadata": {}, "cache_status": {}, "blocks": {"count": 0}}

    monkeypatch.setattr(
        "hotspottriage.cache_generator.generate_full_cache",
        _fake_generate_full_cache,
    )
    start = client.post(
        "/api/cache/generate",
        json={
            "target": str(Path.cwd()),
            "include": "src/**",
            "exclude": "**/tests/**",
        },
    )
    assert start.status_code == 200
    job_id = start.json()["job_id"]
    for _ in range(15):
        status = client.get(f"/api/cache/jobs/{job_id}")
        assert status.status_code == 200
        if status.json()["status"] != "running":
            break
    assert captured["filter"] == "src/**,!**/tests/**"


def test_slim_cache_job_result_omits_row_payloads():
    """Poll JSON must stay small: drop blocks/classes ``results`` lists."""
    heavy = {
        "timestamp": None,
        "target": "/x",
        "filter": None,
        "score_metrics": "a,b",
        "metadata": {"status": "success", "blocks_cached": 2},
        "cache_status": {"entries": 2},
        "blocks": {
            "count": 2,
            "cache": {"entries": 2},
            "results": [{"path": "a::b"}, {"path": "c::d"}],
        },
        "classes": {"count": 3, "results": [{"file": "f.py"}] * 3},
    }
    slim = _slim_cache_job_result(heavy)
    assert "results" not in slim.get("blocks", {})
    assert "results" not in slim.get("classes", {})
    assert slim["blocks"]["count"] == 2
    assert slim["classes"]["count"] == 3
    assert slim["metadata"]["blocks_cached"] == 2


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

    monkeypatch.setattr(
        "hotspottriage.dashboard.server._cache.get_metadata",
        lambda _repo: {"entry_count": 7},
    )
    monkeypatch.setattr(
        "hotspottriage.dashboard.server._cache.load_block_results",
        lambda _repo: None,
    )
    resp = client.post("/api/cache/status", json={"target": str(repo)})
    assert resp.status_code == 200
    data = resp.json()
    assert data["exists"] is True
    assert data["usable"] is False
    assert data["stale"] is True
    assert "regenerate" in data["message"]
    assert data["entries"] == 7


def test_cache_status_rejects_remote_git_url():
    srv = _server()
    client = TestClient(srv.app)
    resp = client.post(
        "/api/cache/status",
        json={"target": "https://github.com/avnovikov/HotspotTriage.git"},
    )
    assert resp.status_code == 400
    assert "local" in str(resp.json().get("detail", "")).lower()


def test_cache_status_hydrates_heatmap_rows_when_cache_exists(monkeypatch, tmp_path):
    srv = _server()
    client = TestClient(srv.app)
    repo = tmp_path / "r"
    repo.mkdir()
    cache_dir = repo / ".hotspottriage" / "cache"
    cache_dir.mkdir(parents=True)
    (cache_dir / "blocks.pkl").write_bytes(b"abc")

    monkeypatch.setattr(
        "hotspottriage.dashboard.server._cache.get_metadata",
        lambda _repo: {"entry_count": 2},
    )
    monkeypatch.setattr(
        "hotspottriage.dashboard.server._cache.load_block_results",
        lambda _repo: [
            _high_raw_block_row("x.py::f"),
            _high_raw_block_row("y.py::g"),
        ],
    )
    status = client.post("/api/cache/status", json={"target": str(repo)})
    assert status.status_code == 200
    heatmap = client.get("/api/stats/heatmap", params={"metric": "score", "limit": 10})
    assert heatmap.status_code == 200
    rows = heatmap.json()["rows"]
    assert len(rows) >= 2
    assert rows[0]["path"] == "x.py::f"


def test_cache_context_persists_locally(tmp_path):
    srv = _server()
    srv._state_file = tmp_path / ".hotspottriage" / "dashboard_state.json"
    client = TestClient(srv.app)
    set_resp = client.post(
        "/api/cache/context",
        json={
            "target": "../LexVox",
            "include": "src/**",
            "exclude": "**/tests/**",
        },
    )
    assert set_resp.status_code == 200
    data = set_resp.json()
    assert data["last_target"] == str((Path.cwd() / "../LexVox").resolve())
    assert data["last_include"] == "src/**"
    assert data["last_exclude"] == "**/tests/**"
    assert data["last_filter"] == "src/**,!**/tests/**"
    assert data["last_score_metrics"] == _default_score_metrics_csv()
    assert data["recent_targets"][0] == str((Path.cwd() / "../LexVox").resolve())
    get_resp = client.get("/api/cache/context")
    assert get_resp.status_code == 200
    assert get_resp.json()["last_include"] == "src/**"


def test_cache_context_legacy_filter_field_still_works(tmp_path):
    srv = _server()
    srv._state_file = tmp_path / ".hotspottriage" / "dashboard_state.json"
    client = TestClient(srv.app)
    set_resp = client.post(
        "/api/cache/context",
        json={
            "target": str(tmp_path),
            "filter": "src/**,!**/tests/**",
        },
    )
    assert set_resp.status_code == 200
    data = set_resp.json()
    assert data["last_filter"] == "src/**,!**/tests/**"
    assert data["last_include"] == "src/**"
    assert data["last_exclude"] == "**/tests/**"
    assert data["last_score_metrics"] == _default_score_metrics_csv()


def test_cache_context_empty_include_uses_default_filter_semantics(tmp_path):
    srv = _server()
    srv._state_file = tmp_path / ".hotspottriage" / "dashboard_state.json"
    client = TestClient(srv.app)
    set_resp = client.post(
        "/api/cache/context",
        json={
            "target": str(tmp_path),
            "include": "",
            "exclude": "",
        },
    )
    assert set_resp.status_code == 200
    assert set_resp.json()["last_filter"] == ""


def test_generate_cache_ignores_score_metrics_request_field(monkeypatch, tmp_path):
    srv = _server()
    client = TestClient(srv.app)
    captured: dict[str, str | None] = {}

    def _fake_generate_full_cache(
        target: str,
        filter: str | None,
        score_metrics: str,
        verbose: bool,
        progress_callback=None,
        config_overrides=None,
    ) -> dict:
        captured["score_metrics"] = score_metrics
        return {"metadata": {}, "cache_status": {}, "blocks": {"count": 0}}

    monkeypatch.setattr(
        "hotspottriage.cache_generator.generate_full_cache",
        _fake_generate_full_cache,
    )
    start = client.post(
        "/api/cache/generate",
        json={
            "target": str(tmp_path),
            "score_metrics": "cyclomatic",
        },
    )
    assert start.status_code == 200
    job_id = start.json()["job_id"]
    for _ in range(15):
        status = client.get(f"/api/cache/jobs/{job_id}")
        assert status.status_code == 200
        if status.json()["status"] != "running":
            break
    assert captured["score_metrics"] == _default_score_metrics_csv()


def test_generate_cache_job_not_found():
    srv = _server()
    client = TestClient(srv.app)
    resp = client.get("/api/cache/jobs/missing")
    assert resp.status_code == 404


def test_stream_endpoints_exist():
    srv = _server()
    client = TestClient(srv.app)
    assert client.get("/dashboard/").status_code == 200
    assert client.get("/dashboard/scores").status_code == 200
    paths = {r.path for r in srv.app.router.routes}
    assert "/api/logs/stream" in paths
    assert "/api/stats/stream" in paths
    assert "/api/config/patch" in paths
    assert "/api/stats/distribution" in paths
    assert "/api/stats/heatmap" in paths
    assert "/dashboard/scores" in paths


def test_stats_heatmap_sorts_and_limits():
    srv = _server()
    srv.publish_latest_block_metrics(
        [
            {"path": "a::x", "score": 0.1, "cyclomatic": 1, "score_band": "low"},
            {"path": "b::y", "score": 0.9, "cyclomatic": 5, "score_band": "critical"},
            {"path": "c::z", "score": 0.5, "cyclomatic": 9, "score_band": "medium"},
        ]
    )
    client = TestClient(srv.app)
    data = client.get("/api/stats/heatmap", params={"limit": 2}).json()
    assert data["limit"] == 2
    assert len(data["rows"]) == 2
    assert data["rows"][0]["path"] == "b::y"
    assert data["rows"][0]["file"] == "b"
    assert data["rows"][0]["method"] == "y"
    assert "score" in data["rows"][0]
    assert data["rows"][1]["path"] == "c::z"


def test_stats_heatmap_column_maxima_excludes_meta_aggregate_row():
    """Meta rows (path ``__...``) must not dominate heatmap tint maxima."""
    srv = _server()
    srv.publish_latest_block_metrics(
        [
            {"path": "__aggregate_similarity__::repo", "score": 0.99, "complexity_burden": 0.95},
            {"path": "a.py::f", "score": 0.4, "complexity_burden": 0.3},
            {"path": "b.py::g", "score": 0.2, "complexity_burden": 0.5},
        ]
    )
    client = TestClient(srv.app)
    data = client.get("/api/stats/heatmap").json()
    assert "column_maxima" in data
    assert data["column_maxima"]["score"] == pytest.approx(0.4)
    assert data["column_maxima"]["complexity_burden"] == pytest.approx(0.5)


def test_stats_heatmap_file_then_method_sort():
    srv = _server()
    srv.publish_latest_block_metrics(
        [
            {"path": "z.py::b", "score": 0.2},
            {"path": "z.py::a", "score": 0.3},
            {"path": "a.py::c", "score": 0.1},
        ]
    )
    client = TestClient(srv.app)
    data = client.get("/api/stats/heatmap").json()
    assert [r["path"] for r in data["rows"]] == ["z.py::a", "z.py::b", "a.py::c"]
    assert "columns" in data


def test_stats_heatmap_empty_rows():
    srv = _server()
    client = TestClient(srv.app)
    empty = client.get("/api/stats/heatmap").json()
    assert empty["rows"] == []


def test_stats_heatmap_rejects_bad_limit():
    srv = _server()
    client = TestClient(srv.app)
    assert client.get("/api/stats/heatmap", params={"limit": 0}).status_code == 400
    assert client.get("/api/stats/heatmap", params={"limit": 501}).status_code == 400


def test_stats_distribution_empty_and_unknown():
    srv = _server()
    client = TestClient(srv.app)
    empty_metric = client.get("/api/stats/distribution", params={"metric": ""}).json()
    assert empty_metric["buckets"] == [] and empty_metric["counts"] == []
    unknown = client.get("/api/stats/distribution", params={"metric": "nope"}).json()
    assert unknown["buckets"] == [] and unknown["counts"] == []


def test_stats_distribution_histogram_counts():
    srv = _server()
    srv.publish_latest_block_metrics(
        [
            {"cyclomatic": 2, "sloc": 10, "score": 0.5},
            {"cyclomatic": 8, "sloc": 12, "score": 0.2},
            {"cyclomatic": 8, "sloc": 9, "score": 0.1},
        ]
    )
    client = TestClient(srv.app)
    data = client.get("/api/stats/distribution", params={"metric": "cyclomatic"}).json()
    assert data["metric"] == "cyclomatic"
    assert sum(data["counts"]) == 3
    assert len(data["buckets"]) == len(data["counts"])


def test_config_patch_persists_and_merges_get(tmp_path):
    patch_path = tmp_path / ".hotspottriage" / "dashboard_config_patch.yml"
    srv = _server(config_patch_path=patch_path)
    client = TestClient(srv.app)
    cyclo_before = client.get("/api/config").json()["metric_normalization"]["cyclomatic"][
        "breakpoints"
    ][1][0]
    resp = client.post(
        "/api/config/patch",
        json={
            "score_aggregation": {
                "complexity_weights": {"cyclomatic": 0.99},
            },
        },
    )
    assert resp.status_code == 200
    merged = client.get("/api/config").json()
    assert merged["score_aggregation"]["complexity_weights"]["cyclomatic"] == 0.99
    assert merged["metric_normalization"]["cyclomatic"]["breakpoints"][1][0] == cyclo_before
    assert patch_path.exists()


def test_generate_cache_uses_saved_score_config_patch(monkeypatch, tmp_path):
    patch_path = tmp_path / ".hotspottriage" / "dashboard_config_patch.yml"
    srv = _server(config_patch_path=patch_path)
    client = TestClient(srv.app)
    saved_edges = [0.2, 0.5, 0.7]
    patch = client.post(
        "/api/config/patch",
        json={"score_aggregation": {"band_edges": saved_edges}},
    )
    assert patch.status_code == 200

    captured: dict[str, dict] = {}

    def _fake_generate_full_cache(
        target: str,
        filter: str | None,
        score_metrics: str,
        verbose: bool,
        progress_callback=None,
        config_overrides=None,
    ) -> dict:
        captured["config_overrides"] = config_overrides or {}
        return {
            "metadata": {"blocks_cached": 1, "classes_indexed": 0},
            "cache_status": {"entries": 1},
            "blocks": {
                "count": 1,
                "results": [_high_raw_block_row()],
            },
        }

    monkeypatch.setattr(
        "hotspottriage.cache_generator.generate_full_cache",
        _fake_generate_full_cache,
    )
    start = client.post("/api/cache/generate", json={"target": str(tmp_path)})
    assert start.status_code == 200
    job_id = start.json()["job_id"]
    for _ in range(10):
        status = client.get(f"/api/cache/jobs/{job_id}")
        assert status.status_code == 200
        if status.json()["status"] != "running":
            break
    assert status.json()["status"] == "done"
    assert captured["config_overrides"]["score_aggregation"]["band_edges"] == saved_edges
    assert captured["config_overrides"]["metric_normalization"]


def test_publish_latest_block_metrics_derives_bands_from_saved_config(tmp_path):
    patch_path = tmp_path / ".hotspottriage" / "dashboard_config_patch.yml"
    srv = _server(config_patch_path=patch_path)
    client = TestClient(srv.app)
    raw_rows = [_high_raw_block_row()]

    resp = client.post(
        "/api/config/patch",
        json={"score_aggregation": {"band_edges": [0.2, 0.5, 0.95]}},
    )
    assert resp.status_code == 200
    srv.publish_latest_block_metrics(raw_rows)
    high_rows = client.get("/api/stats/heatmap").json()["rows"]
    assert high_rows[0]["score_band"] == "high"

    resp = client.post(
        "/api/config/patch",
        json={"score_aggregation": {"band_edges": [0.2, 0.5, 0.7]}},
    )
    assert resp.status_code == 200
    srv.publish_latest_block_metrics(raw_rows)
    critical_rows = client.get("/api/stats/heatmap").json()["rows"]
    assert critical_rows[0]["score_band"] == "critical"


def test_config_patch_validation_error():
    srv = _server()
    client = TestClient(srv.app)
    bad = client.post(
        "/api/config/patch",
        json={
            "metric_normalization": {
                "cyclomatic": {"method": "piecewise", "breakpoints": [[0, 0]]},
            },
        },
    )
    assert bad.status_code == 400


def test_config_patch_rejects_unknown_keys():
    srv = _server()
    client = TestClient(srv.app)
    resp = client.post("/api/config/patch", json={"filter": []})
    assert resp.status_code == 422


def test_config_patch_accepts_proposed_models(tmp_path):
    patch_path = tmp_path / ".hotspottriage" / "dashboard_config_patch.yml"
    srv = _server(config_patch_path=patch_path)
    client = TestClient(srv.app)
    resp = client.post(
        "/api/config/patch",
        json={
            "proposed_models": {
                "low": "gpt-4o-mini",
                "medium": "gpt-4.1",
                "high": "o3",
                "critical": "o3-pro",
            }
        },
    )
    assert resp.status_code == 200
    merged = client.get("/api/config").json()
    assert merged["proposed_models"]["critical"] == "o3-pro"


def test_start_runs_daemon_thread(monkeypatch):
    srv = _server()

    async def _fake_serve(self) -> bool:
        return True

    monkeypatch.setattr("uvicorn.Server.serve", _fake_serve)
    srv.start()
    assert srv._thread is not None
    assert srv._thread.daemon is True
    srv._thread.join(timeout=1.0)
