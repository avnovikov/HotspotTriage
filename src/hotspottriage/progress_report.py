"""Optional terminal progress reporting (stderr only).

Uses Rich when available so we do not add a second progress implementation.
Falls back to no-op if Rich is missing (should not happen with normal installs).
"""
from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager

ProgressCallback = Callable[[str, int, int], None]


def stderr_progress_enabled() -> bool:
    return sys.stderr.isatty()


@contextmanager
def progress_runner(
    enabled: bool, *, description: str = "Working…"
) -> Iterator[ProgressCallback | None]:
    """Yield a callback(task_id, completed, total) or None when disabled."""
    if not enabled or not stderr_progress_enabled():
        yield None
        return

    try:
        from rich.console import Console
        from rich.progress import (
            BarColumn,
            Progress,
            SpinnerColumn,
            TextColumn,
            TimeElapsedColumn,
        )
    except ImportError:
        yield None
        return

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        transient=True,
        console=Console(stderr=True),
    ) as progress:
        task_id = progress.add_task(description, total=1)

        def _cb(task_desc: str, completed: int, total: int) -> None:
            progress.update(task_id, description=task_desc, completed=completed, total=total)

        yield _cb
