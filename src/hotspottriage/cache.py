"""Per-block churn cache stored in <repo>/.hotspottriage/cache/ as pickle files.

Keyed by `(file_blob_sha, start, end, since, until)`. Because the key includes
the file's blob SHA at HEAD, any commit that touches the file invalidates its
cache entries automatically; commits that don't touch a file leave its cache
entries valid.

Cache metadata is stored in metadata.json with timestamps to detect staleness.
"""
from __future__ import annotations

import os
import pickle
import tempfile
from pathlib import Path

from hotspottriage import timestamps


def cache_path_for(repo: Path) -> Path:
    """Return the cache directory for the given repo (under .hotspottriage/cache/)."""
    return repo / ".hotspottriage" / "cache"


class Cache:
    def __init__(self, repo: Path):
        self.repo = repo
        self.dir = cache_path_for(repo)
        self.data: dict[str, int] = {}
        self.dirty = False
        self._load()

    def _load(self) -> None:
        """Load cache from all .pkl files in the cache directory."""
        if not self.dir.exists():
            return
        for pkl_file in self.dir.glob("*.pkl"):
            try:
                with open(pkl_file, "rb") as f:
                    cached = pickle.load(f)
                    if isinstance(cached, dict):
                        self.data.update(cached)
            except (OSError, pickle.UnpicklingError):
                pass

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
        self.dir.mkdir(parents=True, exist_ok=True)
        cache_file = self.dir / "blocks.pkl"
        # Atomic write so a crash mid-save doesn't corrupt the cache file.
        fd, tmp = tempfile.mkstemp(dir=self.dir, prefix=".cache-", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                pickle.dump(self.data, f)
            os.replace(tmp, cache_file)
            # Save metadata with timestamp
            self._save_metadata()
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        self.dirty = False

    def _save_metadata(self) -> None:
        """Save cache metadata including generation timestamp."""
        metadata = {
            "generated_at": timestamps.int_timestamp_now(),
            "entry_count": len(self.data),
            "version": 1,
        }
        timestamps.save_metadata_simple(self.dir, metadata)

    def get_metadata(self) -> dict[str, int | str] | None:
        """Get cache metadata.

        Returns:
            Dictionary with cache metadata, or None if not found
        """
        return timestamps.load_metadata_simple(self.dir)

    def age_seconds(self) -> int | None:
        """Get cache age in seconds since generation.

        Returns:
            Age in seconds, or None if metadata not found
        """
        metadata = self.get_metadata()
        if not metadata or "generated_at" not in metadata:
            return None
        return timestamps.age_seconds(metadata["generated_at"])
