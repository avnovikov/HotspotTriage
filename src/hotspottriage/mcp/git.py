"""Small git subprocess helpers for MCP analyze metadata."""
from __future__ import annotations

import subprocess
from pathlib import Path


def git_short_object_name(repo: Path, full_sha: str) -> str | None:
    token = full_sha.strip()
    if not token:
        return None
    proc = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--short", f"{token}^{{commit}}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    lines = proc.stdout.strip().splitlines()
    return lines[0].strip() if lines else None


def git_live_head_and_branch(repo: Path) -> tuple[str | None, str | None]:
    """Return ``(short HEAD sha, branch name or ``detached``)`` for a local repo."""
    proc = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None, None
    short_head = (proc.stdout.strip().splitlines() or [""])[0].strip() or None
    br = subprocess.run(
        ["git", "-C", str(repo), "branch", "--show-current"],
        check=False,
        capture_output=True,
        text=True,
    )
    branch = (br.stdout.strip().splitlines() or [""])[0].strip()
    if not branch:
        branch = "detached"
    return short_head, branch
