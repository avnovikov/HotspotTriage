"""Tiny JSON cache for per-block churn values.

Keyed by `(file_blob_sha, start, end, since, until)`. Because the key includes
the file's blob SHA at HEAD, any commit that touches the file invalidates its
cache entries automatically; commits that don't touch a file leave its cache
entries valid.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path


def cache_path_for(repo: Path) -> Path:
    h = hashlib.sha256(str(repo.resolve()).encode()).hexdigest()[:16]
    base = Path(os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache"))
    return base / "code-complexity-py" / f"{h}.json"


class Cache:
    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, int] = {}
        self.dirty = False
        if path.exists():
            try:
                self.data = json.loads(path.read_text())
                if not isinstance(self.data, dict):
                    self.data = {}
            except (OSError, ValueError):
                self.data = {}

    @staticmethod
    def make_key(blob_sha: str, start: int, end: int, since: str | None, until: str | None) -> str:
        return f"{blob_sha}:{start}:{end}:{since or ''}:{until or ''}"

    def get(self, key: str) -> int | None:
        return self.data.get(key)

    def put(self, key: str, value: int) -> None:
        self.data[key] = value
        self.dirty = True

    def save(self) -> None:
        if not self.dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write so a crash mid-save doesn't corrupt the cache file.
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".cache-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(self.data, f)
            os.replace(tmp, self.path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        self.dirty = False
