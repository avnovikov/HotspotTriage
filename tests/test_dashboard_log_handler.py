"""Tests for hotspottriage.dashboard.log_handler."""
from __future__ import annotations

import concurrent.futures
import logging
import threading

import pytest

from hotspottriage.dashboard.log_handler import MemoryLogHandler


def _emit(handler: MemoryLogHandler, i: int) -> None:
    handler.emit(
        logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=f"m{i}",
            args=(),
            exc_info=None,
        )
    )


def test_ring_buffer_drops_oldest():
    h = MemoryLogHandler(max_records=3)
    for i in range(5):
        _emit(h, i)
    lm = h.get_log_messages(from_idx=0)
    # Only last 3 lines kept; indices 3,4,5 (1-based counter after 5 emits)
    assert len(lm.messages) == 3
    joined = "".join(lm.messages)
    assert "m0" not in joined and "m1" not in joined
    assert "m4" in joined
    assert lm.max_idx == 5


def test_incremental_from_idx():
    h = MemoryLogHandler(max_records=100)
    _emit(h, 1)
    a = h.get_log_messages(from_idx=0)
    assert len(a.messages) == 1
    assert a.max_idx == 1
    b = h.get_log_messages(from_idx=a.max_idx)
    assert b.messages == []
    assert b.max_idx == 1
    _emit(h, 2)
    c = h.get_log_messages(from_idx=a.max_idx)
    assert len(c.messages) == 1
    assert c.max_idx == 2


def test_clear_then_max_idx_never_decreases():
    h = MemoryLogHandler(max_records=100)
    _emit(h, 0)
    m1 = h.get_log_messages(0).max_idx
    h.clear_log_messages()
    m2 = h.get_log_messages(0).max_idx
    assert m2 == m1
    _emit(h, 1)
    m3 = h.get_log_messages(0).max_idx
    assert m3 > m2


def test_concurrent_emit():
    h = MemoryLogHandler(max_records=10_000)
    barrier = threading.Barrier(8)

    def worker(i: int) -> None:
        barrier.wait()
        for j in range(50):
            _emit(h, i * 1000 + j)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(worker, range(8)))

    lm = h.get_log_messages(from_idx=0)
    assert len(lm.messages) == 400
    assert lm.max_idx == 400


def test_rejects_zero_max_records():
    with pytest.raises(ValueError, match="max_records"):
        MemoryLogHandler(max_records=0)
