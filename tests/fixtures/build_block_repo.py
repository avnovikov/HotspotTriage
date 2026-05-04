"""Build a tiny git repo with classes + methods + a top-level function for
block-level tests."""
from __future__ import annotations

import subprocess
from pathlib import Path


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


_V1 = """\
def top():
    return 1


class Foo:
    def bar(self, x):
        if x:
            return 1
        return 0

    def baz(self):
        return 2
"""

_V2 = """\
def top():
    return 1


class Foo:
    def bar(self, x):
        if x > 0:
            for i in range(x):
                if i % 2:
                    print(i)
        return x

    def baz(self):
        return 3
"""


def build_block_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "commit.gpgsign", "false")

    f = root / "mod.py"
    f.write_text(_V1)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "v1")

    f.write_text(_V2)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "v2: rewrite Foo.bar, tweak Foo.baz")
    return root
