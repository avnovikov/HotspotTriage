"""File discovery: list tracked files in a local repo, or clone a remote URL."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from urllib.parse import urlparse


def is_git_url(target: str) -> bool:
    """Detect remote git URLs (http(s), ssh, git protocol, scp-like)."""
    if target.startswith(("git@", "ssh://", "git://")):
        return True
    if "://" in target:
        scheme = urlparse(target).scheme
        return scheme in {"http", "https", "git", "ssh"}
    return False


@contextmanager
def resolve_target(target: str) -> Iterator[Path]:
    """Yield a local Path for the target. Clones remote URLs to a temp dir
    and removes the temp dir on exit."""
    if is_git_url(target):
        tmp = Path(tempfile.mkdtemp(prefix=f"code-complexity-py-{os.getpid()}-"))
        try:
            subprocess.run(
                ["git", "clone", "--quiet", target, str(tmp)],
                check=True,
            )
            yield tmp
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return

    p = Path(target).expanduser().resolve()
    if not p.is_dir():
        raise NotADirectoryError(f"target is not a directory: {p}")
    if not (p / ".git").exists():
        raise RuntimeError(f"target is not a git repository: {p}")
    yield p


def list_tracked_files(repo: Path) -> list[str]:
    """Return tracked files (relative POSIX paths), via `git ls-files`."""
    result = subprocess.run(
        ["git", "-C", str(repo), "ls-files"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line]
