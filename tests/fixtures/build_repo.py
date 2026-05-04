"""Build a tiny git repo on the fly for tests."""
from __future__ import annotations

import subprocess
from pathlib import Path


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def build_repo(root: Path) -> Path:
    """Create a repo with three files and known per-file commit counts:

      a.py: 3 commits     (cyclomatic = 2)
      b.py: 1 commit      (cyclomatic = 1)
      c/d.py: 2 commits   (cyclomatic = 3)
    """
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "commit.gpgsign", "false")

    a = root / "a.py"
    b = root / "b.py"
    sub = root / "c"
    sub.mkdir()
    d = sub / "d.py"

    # commit 1: add a.py and b.py
    a.write_text("x = 1\n")
    b.write_text("def b():\n    return 1\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "c1")

    # commit 2: edit a.py
    a.write_text("def a(x):\n    if x:\n        return x\n    return 0\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "c2")

    # commit 3: add c/d.py, edit a.py
    a.write_text("def a(x):\n    if x:\n        return x\n    return -1\n")
    d.write_text(
        "def d(x):\n"
        "    if x > 0:\n"
        "        return 1\n"
        "    elif x < 0:\n"
        "        return -1\n"
        "    return 0\n"
    )
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "c3")

    # commit 4: edit a.py and c/d.py (touches both)
    a.write_text("def a(x):\n    if x:\n        return x\n    return None\n")
    d.write_text(
        "def d(x):\n"
        "    if x > 0:\n"
        "        return 1\n"
        "    elif x < 0:\n"
        "        return -1\n"
        "    else:\n"
        "        return 0\n"
    )
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "c4")

    # Final churn: a.py=3 (commits 1,2,3,4 -> wait, 4 commits touched a.py).
    # Recount:
    #   a.py: c1, c2, c3, c4 -> 4
    #   b.py: c1 -> 1
    #   c/d.py: c3, c4 -> 2
    return root
