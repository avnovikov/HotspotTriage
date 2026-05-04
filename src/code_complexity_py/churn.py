"""Churn = number of commits touching each file, via `git log --name-only`."""
from __future__ import annotations

import subprocess
from collections import Counter
from pathlib import Path


def compute_churn(
    repo: Path,
    since: str | None = None,
    until: str | None = None,
) -> dict[str, int]:
    """Count commits touching each tracked file across the whole repo history.

    Note: we deliberately do NOT pass `--follow`, because `--follow` only works
    when given a single pathspec. The original Node tool runs git log per-file
    with `--follow`; doing one global log here is far cheaper for large repos
    and gives the same churn count except across renames. For our use case
    (rough indicator of how often a file is touched) this is the right tradeoff.
    """
    cmd = ["git", "-C", str(repo), "log", "--format=", "--name-only"]
    if since:
        cmd.append(f"--since={since}")
    if until:
        cmd.append(f"--until={until}")
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    counts: Counter[str] = Counter(line for line in result.stdout.splitlines() if line)
    return dict(counts)
