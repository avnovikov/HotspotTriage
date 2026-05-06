"""Tests for embedded dashboard HTML."""
from hotspottriage.dashboard.html import DASHBOARD_HTML


def test_dashboard_html_contains_required_panels():
    assert "Config Overview" in DASHBOARD_HTML
    assert "Tool Call Statistics" in DASHBOARD_HTML
    assert "Log Viewer" in DASHBOARD_HTML
    assert "healthBadge" in DASHBOARD_HTML
    assert "cacheContextPanel" in DASHBOARD_HTML
    assert "Build Parameters:" in DASHBOARD_HTML


def test_dashboard_html_is_self_contained():
    assert "<style>" in DASHBOARD_HTML
    assert "<script>" in DASHBOARD_HTML
    assert "EventSource(\"/api/logs/stream\")" in DASHBOARD_HTML
    assert "setInterval(refreshStats, 5000)" in DASHBOARD_HTML
    assert "/api/cache/context" in DASHBOARD_HTML
