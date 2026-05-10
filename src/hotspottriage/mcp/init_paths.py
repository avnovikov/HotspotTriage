"""Normalize ``init_config`` written-path return values to string lists."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path


def paths_written_as_str_list(written: Path | Iterable[Path]) -> list[str]:
    """``init_config`` may return a single path or an iterable of paths."""
    if isinstance(written, Path):
        return [str(written)]
    return [str(f) for f in written]
