"""Tests for dashboard UI: Jinja2 templates and static JS."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hotspottriage import config as _project_config
from hotspottriage.dashboard.log_handler import MemoryLogHandler
from hotspottriage.dashboard.server import DashboardServer
from hotspottriage.dashboard.stats import StatsCollector


def _server() -> DashboardServer:
    stats = StatsCollector()
    logs = MemoryLogHandler(max_records=100)
    snap = _project_config.to_dashboard_snapshot(dict(_project_config.DEFAULTS))
    return DashboardServer(
        config=snap,
        stats=stats,
        log_handler=logs,
        host="127.0.0.1",
        base_port=9200,
        open_on_start=False,
    )


@pytest.fixture()
def client():
    srv = _server()
    with TestClient(srv.app) as c:
        yield c


# ---------- Jinja2 template-rendered pages (single source for dashboard UI) ----------

def test_overview_page_renders(client):
    """Overview page returns 200 with expected HTML elements."""
    r = client.get("/dashboard/")
    assert r.status_code == 200
    body = r.text
    assert "HotspotTriage Dashboard" in body
    assert "cacheTargetInput" in body
    assert "cacheIncludeInput" in body
    assert "cacheExcludeInput" in body
    assert "cacheSaveCtxBtn" in body
    assert "cacheContextPanel" in body
    assert "overviewSummaryPanel" in body
    assert 'id="logs"' in body
    assert "shared.js" in body
    assert "overview.js" in body


def test_heatmap_page_renders(client):
    """Heatmap page returns 200 with filter input and controls."""
    r = client.get("/dashboard/heatmap")
    assert r.status_code == 200
    body = r.text
    assert "HotspotTriage Dashboard" in body
    assert "heatmapUpdateBtn" in body
    assert "heatmapLimitInput" in body
    assert "heatmapRepoRootDisplay" in body
    assert "heatmapPanel" in body
    assert "heatmapMatrixHost" in body
    assert "heatmapNarrativeTip" in body
    assert "heatmapViewFilterInput" in body
    assert "shared.js" in body
    assert "heatmap.js" in body


def test_config_page_renders(client):
    """Config page returns 200 with config editors."""
    r = client.get("/dashboard/config")
    assert r.status_code == 200
    body = r.text
    assert "HotspotTriage Dashboard" in body
    assert "configPanel" in body
    assert "configSaveBtn" in body
    assert "configRefreshDataBtn" in body
    assert "scoreWeightsPanel" in body
    assert "scoreBandsPanel" in body
    assert "proposedModelsPanel" in body
    assert "statsPanel" in body
    assert "shared.js" in body
    assert "config.js" in body


def test_scores_page_renders(client):
    """Scores page returns 200."""
    r = client.get("/dashboard/scores")
    assert r.status_code == 200
    body = r.text
    assert "HotspotTriage" in body


def test_static_js_shared_accessible(client):
    """shared.js static file is served."""
    r = client.get("/dashboard/static/js/shared.js")
    assert r.status_code == 200
    assert "function escapeHtml" in r.text
    assert "function setTheme" in r.text
    assert "syncHeatmapRepoDisplay" in r.text
    assert "directoryFromConfig" in r.text
    assert "/api/cache/context" in r.text
    assert "/api/config" in r.text
    assert "heatmapRepoRootDisplay" in r.text
    assert "function truncateLeftLabelToWidth" in r.text
    assert "measureText(candidate).width <= maxWidth" in r.text


def test_static_js_heatmap_accessible(client):
    """heatmap.js static file contains filter and render functions."""
    r = client.get("/dashboard/static/js/heatmap.js")
    assert r.status_code == 200
    assert "applyHeatmapPresentationFilter" in r.text
    assert "renderHeatmapPanel" in r.text
    assert "refreshHeatmap" in r.text
    assert "/api/stats/block_narrative" in r.text
    assert "bindHeatmapNarrativeTips" in r.text
    assert "function heatmapColumnHeaderHtml" in r.text
    assert "/api/stats/heatmap" in r.text
    assert "truncateLeftLabelToWidth(r.file" in r.text


def test_static_js_config_accessible(client):
    """config.js static file contains normalization and weight editors."""
    r = client.get("/dashboard/static/js/config.js")
    assert r.status_code == 200
    assert "redrawNormMetric" in r.text
    assert "renderScoreWeights" in r.text
    assert "renderScoreBands" in r.text
    assert "function setFinalWeight" in r.text
    assert "DEFAULT_BAND_EDGES" in r.text
    assert "must be 1.000" in r.text
    assert "final_weights" in r.text


def test_static_js_overview_accessible(client):
    """overview.js static file contains cache and log functions."""
    r = client.get("/dashboard/static/js/overview.js")
    assert r.status_code == 200
    assert "generateCache" in r.text
    assert "checkCacheStatus" in r.text
    assert "connectLogStream" in r.text
    assert 'EventSource("/api/logs/stream")' in r.text


def test_per_screen_templates_exist():
    """All per-screen Jinja2 template files exist on disk."""
    templates_dir = Path(__file__).resolve().parent.parent / "src" / "hotspottriage" / "dashboard" / "templates"
    assert (templates_dir / "base.html").is_file()
    assert (templates_dir / "overview.html").is_file()
    assert (templates_dir / "heatmap.html").is_file()
    assert (templates_dir / "config.html").is_file()
    assert (templates_dir / "scores.html").is_file()


def test_per_screen_static_js_exist():
    """All per-screen JS files exist on disk."""
    js_dir = Path(__file__).resolve().parent.parent / "src" / "hotspottriage" / "dashboard" / "static" / "js"
    assert (js_dir / "shared.js").is_file()
    assert (js_dir / "overview.js").is_file()
    assert (js_dir / "heatmap.js").is_file()
    assert (js_dir / "config.js").is_file()


def test_heatmap_page_has_presentation_filter(client):
    """Issue #72: heatmap page includes the presentation filter input."""
    r = client.get("/dashboard/heatmap")
    body = r.text
    assert "heatmapViewFilterInput" in body
    assert "path or function" in body


def test_each_page_has_independent_nav(client):
    """Each page renders the nav bar for cross-screen navigation."""
    for path in ["/dashboard/", "/dashboard/heatmap", "/dashboard/config"]:
        r = client.get(path)
        assert r.status_code == 200
        body = r.text
        assert "topNav" in body
        assert "healthBadge" in body
        assert "themeToggle" in body
