"""In-memory ring buffer logging handler for the dashboard."""
from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class LogMessages:
    """Incremental log fetch: messages newer than ``from_idx``, plus current ``max_idx``."""

    messages: list[str]
    max_idx: int


class MemoryLogHandler(logging.Handler):
    """Thread-safe ring buffer of formatted log lines for SSE / polling."""

    def __init__(self, max_records: int = 1000) -> None:
        super().__init__()
        if max_records < 1:
            raise ValueError(f"max_records must be >= 1; got {max_records}")
        self._maxlen = int(max_records)
        self._records: deque[tuple[int, str]] = deque(maxlen=self._maxlen)
        self._counter = 0
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
        except Exception:
            msg = record.getMessage()
        with self._lock:
            self._counter += 1
            self._records.append((self._counter, msg))

    def get_log_messages(self, from_idx: int = 0) -> LogMessages:
        """Return messages with index strictly greater than ``from_idx``."""
        with self._lock:
            filtered = [msg for idx, msg in self._records if idx > int(from_idx)]
            max_idx = self._counter
        return LogMessages(messages=filtered, max_idx=max_idx)

    def clear_log_messages(self) -> None:
        """Drop buffered lines; indices for new lines continue after the current counter."""
        with self._lock:
            self._records.clear()
