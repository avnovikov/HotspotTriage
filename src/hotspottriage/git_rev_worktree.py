"""Detached git worktrees for analyzing a commit without mutating the main checkout."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def resolve_rev(repo: Path, rev: str) -> str:
    """Return the full 40-hex object name for *rev* (branch, tag, SHA, ``HEAD~1``, …)."""
    token = rev.strip()
    if not token:
        raise ValueError("rev must be non-empty")
    proc = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "rev-parse",
            "--verify",
            f"{token}^" + "{commit}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise ValueError(f"invalid git rev {rev!r}: {err}" if err else f"invalid git rev {rev!r}")
    sha = proc.stdout.strip().splitlines()[0].strip()
    if not sha:
        raise ValueError(f"git rev-parse returned empty output for {rev!r}")
    return sha


@contextmanager
def detached_worktree(repo: Path, rev: str) -> Iterator[Path]:
    """Materialise *rev* as a detached worktree directory; remove it on exit.

    The worktree is created under a temporary directory so paths stay unique
    across concurrent MCP calls.
    """
    repo = repo.resolve()
    sha = resolve_rev(repo, rev)
    parent = Path(tempfile.mkdtemp(prefix="hotspottriage-wt-"))
    wt = parent / "wt"
    try:
        subprocess.run(
            ["git", "-C", str(repo), "worktree", "add", "--detach", str(wt), sha],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        shutil.rmtree(parent, ignore_errors=True)
        err = (e.stderr or e.stdout or "").strip()
        raise RuntimeError(f"git worktree add failed: {err}") from e
    try:
        yield wt.resolve()
    finally:
        subprocess.run(
            ["git", "-C", str(repo), "worktree", "remove", "--force", str(wt)],
            check=False,
            capture_output=True,
        )
        shutil.rmtree(parent, ignore_errors=True)
