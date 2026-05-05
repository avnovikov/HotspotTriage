"""Tiny repo with two files containing intentionally similar top-level functions."""
from __future__ import annotations

import subprocess
from pathlib import Path


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def build_similarity_repo(root: Path) -> Path:
    """Two modules with nearly identical ``twin`` implementations for DeepCSIM."""
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "commit.gpgsign", "false")

    a = root / "a.py"
    b = root / "b.py"
    a.write_text(
        "def twin(x):\n"
        "    if x > 0:\n"
        "        return x * 2\n"
        "    return 0\n"
    )
    b.write_text(
        "def twin(y):\n"
        "    if y > 0:\n"
        "        return y * 2\n"
        "    return 0\n"
    )
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "similar twins")
    return root
