"""Block-level results cache stored in <repo>/.hotspottriage/cache/blocks.pkl.

Each row is a full Statistic-as-dict with ``_blob_sha``, ``_start``, and
``_end`` fields for staleness detection.  When the file's blob SHA at HEAD
matches the stored one, churn (and all derived metrics) are reusable.

Cache metadata is stored in metadata.json with timestamps.
"""
from __future__ import annotations

import os
import pickle
import tempfile
from pathlib import Path

from hotspottriage import timestamps

_CACHE_FILE = "blocks.pkl"


def cache_path_for(repo: Path) -> Path:
    """Return the cache directory for the given repo (under .hotspottriage/cache/)."""
    return repo / ".hotspottriage" / "cache"


def save_block_results(repo: Path, rows: list[dict]) -> None:
    """Persist full block metric rows to disk (atomic write)."""
    cache_dir = cache_path_for(repo)
    cache_dir.mkdir(parents=True, exist_ok=True)
    results_file = cache_dir / _CACHE_FILE
    fd, tmp = tempfile.mkstemp(dir=cache_dir, prefix=".cache-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            pickle.dump(rows, f)
        os.replace(tmp, results_file)
        _save_metadata(cache_dir, len(rows))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_block_results(repo: Path) -> list[dict] | None:
    """Load persisted block metric rows, or ``None`` if unavailable."""
    results_file = cache_path_for(repo) / _CACHE_FILE
    if not results_file.exists():
        return None
    try:
        with open(results_file, "rb") as f:
            data = pickle.load(f)
        return data if isinstance(data, list) else None
    except (OSError, pickle.UnpicklingError):
        return None


def get_metadata(repo: Path) -> dict[str, int | str] | None:
    """Get cache metadata (generated_at, entry_count, version)."""
    return timestamps.load_metadata_simple(cache_path_for(repo))


def age_seconds(repo: Path) -> int | None:
    """Get cache age in seconds since generation."""
    metadata = get_metadata(repo)
    if not metadata or "generated_at" not in metadata:
        return None
    return timestamps.age_seconds(metadata["generated_at"])


def _save_metadata(cache_dir: Path, entry_count: int) -> None:
    metadata = {
        "generated_at": timestamps.int_timestamp_now(),
        "entry_count": entry_count,
        "version": 2,
    }
    timestamps.save_metadata_simple(cache_dir, metadata)
