"""Churn = total lines (added + deleted) summed across all commits, per file.

Computed via a single `git log --numstat`. Binary files (numstat columns are
`-`) are excluded. Renames are not followed (`--follow` only works per-file
and would force one git invocation per path); a renamed file's pre-rename
churn stays attached to its old name.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


def compute_churn(
    repo: Path,
    since: str | None = None,
    until: str | None = None,
) -> dict[str, int]:
    cmd = ["git", "-C", str(repo), "log", "--format=", "--numstat"]
    if since:
        cmd.append(f"--since={since}")
    if until:
        cmd.append(f"--until={until}")
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)

    counts: dict[str, int] = {}
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added, deleted, path = parts
        if added == "-" or deleted == "-":
            continue  # binary file
        try:
            counts[path] = counts.get(path, 0) + int(added) + int(deleted)
        except ValueError:
            continue
    return counts


def get_file_timestamps(
    repo: Path,
    files: list[str],
) -> dict[str, int]:
    """Get the Unix timestamp of the last commit touching each file.
    
    Args:
        repo: Repository root path
        files: List of file paths relative to repo
    
    Returns:
        Dict mapping file paths to Unix timestamps of last commit
    """
    timestamps: dict[str, int] = {}
    for file_path in files:
        try:
            result = subprocess.run(
                ["git", "-C", str(repo), "log", "-1", "--format=%ct", "--", file_path],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                timestamps[file_path] = int(result.stdout.strip())
        except (ValueError, OSError):
            timestamps[file_path] = 0
    return timestamps
