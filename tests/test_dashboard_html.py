"""Tests for embedded dashboard HTML."""
from hotspottriage.dashboard.html import DASHBOARD_HTML


def test_dashboard_html_contains_required_panels():
    assert "Summary" in DASHBOARD_HTML
    assert "Configuration Editors" in DASHBOARD_HTML
    assert "Tool Call Statistics" in DASHBOARD_HTML
    assert "Log Viewer" in DASHBOARD_HTML
    assert "healthBadge" in DASHBOARD_HTML
    assert "cacheContextPanel" in DASHBOARD_HTML
    assert "Build Parameters:" in DASHBOARD_HTML
    assert "configSaveBtn" in DASHBOARD_HTML
    assert "configRefreshDataBtn" in DASHBOARD_HTML
    assert "Save config" in DASHBOARD_HTML
    assert "Refresh data" in DASHBOARD_HTML
    assert "No data yet" in DASHBOARD_HTML
    assert "scoreWeightsPanel" in DASHBOARD_HTML
    assert "scoreBandsPanel" in DASHBOARD_HTML
    assert "norm-metric-card" in DASHBOARD_HTML
    assert "weight-sum-badge" in DASHBOARD_HTML
    assert "heatmapUpdateBtn" in DASHBOARD_HTML
    assert "heatmapTargetInput" in DASHBOARD_HTML
    assert "heatmapFilterInput" in DASHBOARD_HTML
    assert "heatmapScoreInput" in DASHBOARD_HTML
    assert "heatmapLimitInput" in DASHBOARD_HTML


def test_dashboard_html_hash_routing_and_heatmap():
    assert 'id="view-overview"' in DASHBOARD_HTML
    assert 'id="view-heatmap"' in DASHBOARD_HTML
    assert 'id="view-config"' in DASHBOARD_HTML
    assert 'data-route="overview"' in DASHBOARD_HTML
    assert 'href="#overview"' in DASHBOARD_HTML
    assert 'href="#heatmap"' in DASHBOARD_HTML
    assert 'href="#config"' in DASHBOARD_HTML
    assert 'id="topNav"' in DASHBOARD_HTML
    assert "overviewSummaryPanel" in DASHBOARD_HTML
    assert "heatmapPanel" in DASHBOARD_HTML
    assert "updateHeatmapData" in DASHBOARD_HTML
    assert "initRouting()" in DASHBOARD_HTML
    assert "/api/stats/heatmap" in DASHBOARD_HTML
    assert "heatmapColumnHeaderHtml" in DASHBOARD_HTML
    assert "#view-config .norm-svg-wrap" in DASHBOARD_HTML
    assert "normChartTabWidth" in DASHBOARD_HTML
    assert ".heatmap-file-col .heatmap-file-label" in DASHBOARD_HTML
    assert "function truncateLeftLabelToWidth(value, maxWidthPx = 168)" in DASHBOARD_HTML
    assert "measureText(candidate).width <= maxWidth" in DASHBOARD_HTML
    assert "truncateLeftLabelToWidth(r.file || \"\")" in DASHBOARD_HTML
    assert "Necessary when configuration changes." in DASHBOARD_HTML


def test_dashboard_html_is_self_contained():
    assert "<style>" in DASHBOARD_HTML
    assert "<script>" in DASHBOARD_HTML
    assert 'EventSource("/api/logs/stream")' in DASHBOARD_HTML
    assert "setInterval(refreshStats, 5000)" in DASHBOARD_HTML
    assert "/api/cache/context" in DASHBOARD_HTML
    assert "/api/config/patch" in DASHBOARD_HTML
    assert "setInterval(refreshDistributionsOnly, 30000)" in DASHBOARD_HTML


def test_dashboard_html_exposes_score_band_threshold_editor():
    assert "Score band thresholds" in DASHBOARD_HTML
    assert "Risk band handles" in DASHBOARD_HTML
    assert "DEFAULT_BAND_EDGES" in DASHBOARD_HTML
    assert "band_edges" in DASHBOARD_HTML
    assert "band_names" in DASHBOARD_HTML
    assert "renderScoreBands()" in DASHBOARD_HTML
    assert 'data-role="band-slider"' in DASHBOARD_HTML


def test_dashboard_html_exposes_final_burden_weights_editor():
    assert "final_weights" in DASHBOARD_HTML
    assert "top composite parameters (must sum to 1.0)" in DASHBOARD_HTML
    assert "complexity_burden" in DASHBOARD_HTML
    assert "churn_burden" in DASHBOARD_HTML
    assert "maintainability_burden" in DASHBOARD_HTML
    assert "smell_burden" in DASHBOARD_HTML
    assert "similarity_burden" in DASHBOARD_HTML
    assert "setFinalWeight" in DASHBOARD_HTML
    assert "ensureFinalWeights" in DASHBOARD_HTML
    assert "toFixed(2)" in DASHBOARD_HTML
    assert "must be 1.000" in DASHBOARD_HTML
