"""Tests for hotspottriage.dashboard.stats."""
from __future__ import annotations

import concurrent.futures
import threading

import pytest

from hotspottriage.dashboard.stats import StatsCollector, ToolStats


def test_avg_duration_zero_when_no_calls():
    s = ToolStats()
    assert s.avg_duration_ms == 0.0


def test_record_call_tracks_errors_and_duration():
    c = StatsCollector()
    c.record_call("analyze", 10.0, error=False)
    c.record_call("analyze", 30.0, error=True)
    snap = c.get_snapshot()["analyze"]
    assert snap["num_calls"] == 2
    assert snap["num_errors"] == 1
    assert snap["total_duration_ms"] == 40.0
    assert snap["avg_duration_ms"] == 20.0
    assert snap["last_called_at"] is not None


def test_get_snapshot_is_deep_copy():
    c = StatsCollector()
    c.record_call("x", 1.0)
    a = c.get_snapshot()
    b = c.get_snapshot()
    assert a == b
    assert a is not b
    assert a["x"] is not b["x"]


def test_clear_resets():
    c = StatsCollector()
    c.record_call("t", 5.0)
    c.clear()
    assert c.get_snapshot() == {}


def test_concurrent_record_calls():
    c = StatsCollector()
    barrier = threading.Barrier(8)

    def worker() -> None:
        barrier.wait()
        for _ in range(100):
            c.record_call("tool", 1.0, error=False)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(worker) for _ in range(8)]
        for f in futures:
            f.result()

    assert c.get_snapshot()["tool"]["num_calls"] == 800


def test_record_call_rejects_empty_name():
    with pytest.raises(ValueError, match="non-empty"):
        StatsCollector().record_call("", 1.0)


def test_record_call_rejects_negative_duration():
    with pytest.raises(ValueError, match="non-negative"):
        StatsCollector().record_call("x", -1.0)
