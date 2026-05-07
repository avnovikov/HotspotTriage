"""Tests for dashboard heatmap fragment builder."""
from hotspottriage.dashboard.heatmap import build_heatmap_fragment


def test_build_heatmap_fragment_returns_placeholder_for_empty_results():
    fragment = build_heatmap_fragment([])
    assert "No results yet" in fragment
    assert 'class="heatmap"' in fragment


def test_build_heatmap_fragment_groups_and_sorts_by_severity():
    results = [
        {
            "path": "src/a.py::f1",
            "score": 0.35,
            "score_band": "medium",
            "cyclomatic": 2,
            "norm_cyclomatic": 0.2,
        },
        {
            "path": "src/b.py::ClassA.run",
            "score": 0.92,
            "score_band": "critical",
            "cyclomatic": 10,
            "norm_cyclomatic": 0.8,
        },
        {
            "path": "src/b.py::ClassA.slow",
            "score": 0.74,
            "score_band": "high",
            "cyclomatic": 8,
            "norm_cyclomatic": 0.6,
            "norm_unrelated_metric": 0.9,
        },
    ]

    fragment = build_heatmap_fragment(results)
    b_index = fragment.index("src/b.py")
    a_index = fragment.index("src/a.py")
    assert b_index < a_index
    assert "&lt;module&gt;" in fragment
    assert "CLASSA" not in fragment  # preserve symbol case
    assert "ClassA" in fragment
    assert 'data-sort-key="norm_cyclomatic"' in fragment
    assert ">norm_cyclomatic<" in fragment
    assert 'data-sort-key="norm_unrelated_metric"' not in fragment
    assert "SCORE" in fragment
    assert "cyclomatic: 10 -&gt; norm=0.800" in fragment

