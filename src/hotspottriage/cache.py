"""Block-level results cache stored in <repo>/.hotspottriage/cache/blocks.pkl.

Each row stores raw block metrics plus ``_blob_sha``, ``_start``, and ``_end``
fields for staleness detection.  When the file's blob SHA at HEAD matches the
stored one, expensive raw metrics such as churn are reusable; scores and
normalization are derived from the active config at read time.

Cache metadata is stored in metadata.json with timestamps.

``BlockCacheManager`` provides a thread-safe in-memory cache with periodic
disk persistence, inspired by Serena's SolidLSP cache model:

- **Versioned pickle envelope**: rejects stale on-disk data when format changes.
- **Per-entry blob SHA staleness**: same as before; only churn is reused.
- **Modified flag**: avoids redundant disk writes.
- **Periodic flush**: background timer writes dirty state to disk so long
  generation runs don't lose progress and concurrent readers see updates.
"""
from __future__ import annotations

import logging
import os
import pickle
import tempfile
import threading
from pathlib import Path
from typing import Any

from hotspottriage import timestamps
from hotspottriage.filtering import filter_block_rows_excluding_gitignore
from hotspottriage.path_utils import sanitize_log_value

logger = logging.getLogger(__name__)

_CACHE_FILE = "blocks.pkl"

CACHE_VERSION = 4


def cache_path_for(repo: Path) -> Path:
    """Return the cache directory for the given repo (under .hotspottriage/cache/)."""
    return repo / ".hotspottriage" / "cache"


def _write_versioned_pickle(path: Path, rows: list[dict]) -> None:
    """Atomic write of a versioned pickle envelope to *path*."""
    envelope = {"__cache_version": CACHE_VERSION, "obj": rows}
    cache_dir = path.parent
    cache_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=cache_dir, prefix=".cache-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            pickle.dump(envelope, f)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            # Best-effort cleanup of temp file after failed pickle write.
            pass
        raise


def _read_versioned_pickle(path: Path) -> list[dict] | None:
    """Load a versioned pickle; return ``None`` on version mismatch or missing file."""
    if not path.exists():
        return None
    try:
        with open(path, "rb") as f:
            raw = pickle.load(f)
    except (OSError, pickle.UnpicklingError, EOFError):
        return None
    if isinstance(raw, dict) and raw.get("__cache_version") == CACHE_VERSION:
        obj = raw.get("obj")
        return obj if isinstance(obj, list) else None
    if isinstance(raw, list):
        logger.info(
            "Legacy unversioned cache at %s — starting fresh",
            sanitize_log_value(str(path)),
        )
        return None
    logger.info(
        "Cache version mismatch at %s — starting fresh",
        sanitize_log_value(str(path)),
    )
    return None


def save_block_results(
    repo: Path,
    rows: list[dict],
    *,
    respect_gitignore: bool = True,
) -> None:
    """Persist full block metric rows to disk (atomic write, versioned envelope).

    By default, rows whose file path matches the repo ``.gitignore`` (nested
    gitignores / ``info/exclude``) are **not** written — they must not enter
    the on-disk cache used by the dashboard heatmap and MCP.
    """
    filtered = filter_block_rows_excluding_gitignore(
        repo, rows, respect_gitignore=respect_gitignore
    )
    results_file = cache_path_for(repo) / _CACHE_FILE
    _write_versioned_pickle(results_file, filtered)
    _save_metadata(cache_path_for(repo), len(filtered))


def load_block_results(
    repo: Path,
    *,
    respect_gitignore: bool = True,
) -> list[dict] | None:
    """Load persisted block metric rows, or ``None`` if unavailable.

    Gitignored paths are stripped on load (default) so older caches cannot
    resurrect ignored files into the dashboard / analyzers.
    """
    rows = _read_versioned_pickle(cache_path_for(repo) / _CACHE_FILE)
    if rows is None:
        return None
    return filter_block_rows_excluding_gitignore(
        repo, rows, respect_gitignore=respect_gitignore
    )


def block_cache_stats(repo: Path) -> dict[str, Any]:
    """On-disk ``blocks.pkl`` location and size (MCP ``analyze`` ``cache`` shape)."""
    cache_dir = cache_path_for(repo)
    cache_file = cache_dir / _CACHE_FILE
    size_bytes = cache_file.stat().st_size if cache_file.exists() else 0
    rows = load_block_results(repo)
    entries = len(rows) if rows else 0
    return {
        "cache_file": str(cache_file),
        "entries": entries,
        "size_bytes": size_bytes,
    }


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
        "version": CACHE_VERSION,
    }
    timestamps.save_metadata_simple(cache_dir, metadata)


class BlockCacheManager:
    """Thread-safe in-memory block cache with periodic disk persistence.

    Inspired by Serena's SolidLSP cache model:

    - Versioned pickle envelope (``__cache_version``).
    - Per-entry staleness via blob SHA (unchanged from before).
    - ``_modified`` flag gates disk writes.
    - Background timer flushes dirty state to disk periodically so
      concurrent readers (dashboard, MCP queries) see progress during
      long generation runs.

    Typical lifecycle::

        mgr = BlockCacheManager(repo)       # loads from disk
        mgr.start_periodic_flush()          # background thread
        # ... analysis writes rows via put_rows / put_row ...
        mgr.stop()                          # final flush + cancel timer
    """

    def __init__(
        self, repo: Path, *, flush_interval_s: float = 15.0
    ) -> None:
        if not isinstance(repo, Path):
            raise TypeError(f"repo must be a Path; got {type(repo).__name__}")
        self._repo = repo.resolve()
        self._lock = threading.RLock()
        self._rows: dict[str, dict[str, Any]] = {}
        self._modified = False
        self._generation = 0
        self._flush_interval = max(1.0, float(flush_interval_s))
        self._timer: threading.Timer | None = None
        self._stopped = False
        self._load_from_disk()

    @property
    def repo(self) -> Path:
        return self._repo

    @property
    def generation(self) -> int:
        with self._lock:
            return self._generation

    @property
    def modified(self) -> bool:
        with self._lock:
            return self._modified

    @property
    def entry_count(self) -> int:
        with self._lock:
            return len(self._rows)

    def _load_from_disk(self) -> None:
        rows = load_block_results(self._repo)
        if rows is None:
            return
        with self._lock:
            for row in rows:
                if isinstance(row, dict) and "path" in row:
                    self._rows[row["path"]] = row

    def _flush_path(self) -> Path:
        return cache_path_for(self._repo) / _CACHE_FILE

    def _save_to_disk_unlocked(self) -> None:
        """Write current state to disk (caller must hold ``_lock``)."""
        rows = filter_block_rows_excluding_gitignore(
            self._repo, list(self._rows.values()), respect_gitignore=True
        )
        # Keep memory aligned with what we persist.
        self._rows = {
            str(r["path"]): r
            for r in rows
            if isinstance(r, dict) and "path" in r
        }
        _write_versioned_pickle(self._flush_path(), rows)
        _save_metadata(cache_path_for(self._repo), len(rows))

    def get_all_rows(self) -> list[dict[str, Any]]:
        """Return a snapshot of all cached rows (thread-safe copy)."""
        with self._lock:
            return list(self._rows.values())

    def get_previous_rows_index(self) -> dict[str, dict[str, Any]]:
        """Return ``{path: row}`` for churn-reuse lookups (thread-safe copy)."""
        with self._lock:
            return dict(self._rows)

    def get_row(self, path: str) -> dict[str, Any] | None:
        with self._lock:
            return self._rows.get(path)

    def put_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        targeted_files: set[str] | None = None,
    ) -> None:
        """Replace rows for *targeted_files* (or all) with *rows*.

        Rows for files **not** in *targeted_files* are preserved (scoped-run
        semantics, same as the old ``build_block_stats`` merge logic).
        Incoming and preserved rows that match ``.gitignore`` are dropped so
        ignored paths never remain in the block cache.
        """
        filtered_in = filter_block_rows_excluding_gitignore(
            self._repo, rows, respect_gitignore=True
        )
        with self._lock:
            if targeted_files is not None:
                keys_to_remove = [
                    k
                    for k in self._rows
                    if "::" in k and k.split("::", 1)[0] in targeted_files
                ]
                for k in keys_to_remove:
                    del self._rows[k]
            for row in filtered_in:
                if isinstance(row, dict) and "path" in row:
                    self._rows[row["path"]] = row
            # Scrub any preserved entries that are now gitignored.
            scrubbed = filter_block_rows_excluding_gitignore(
                self._repo, list(self._rows.values()), respect_gitignore=True
            )
            self._rows = {
                str(r["path"]): r
                for r in scrubbed
                if isinstance(r, dict) and "path" in r
            }
            self._modified = True
            self._generation += 1

    def put_row(self, row: dict[str, Any]) -> None:
        """Insert or update a single row (thread-safe)."""
        filtered = filter_block_rows_excluding_gitignore(
            self._repo, [row], respect_gitignore=True
        )
        if not filtered:
            return
        row = filtered[0]
        path = row.get("path")
        if path is None:
            return
        with self._lock:
            self._rows[str(path)] = row
            self._modified = True

    def flush(self) -> bool:
        """Flush to disk if modified. Returns ``True`` if data was written."""
        with self._lock:
            if not self._modified:
                return False
            try:
                self._save_to_disk_unlocked()
            except Exception:
                logger.exception("BlockCacheManager: flush failed")
                return False
            self._modified = False
            return True

    def clear(self) -> None:
        """Drop all in-memory rows and remove the on-disk cache file."""
        with self._lock:
            self._rows.clear()
            self._modified = False
            self._generation += 1
        cache_file = self._flush_path()
        try:
            if cache_file.exists():
                cache_file.unlink()
        except OSError:
            # Ignore missing file or concurrent delete.
            pass

    def start_periodic_flush(self) -> None:
        """Begin a repeating background flush timer."""
        if self._stopped:
            return

        def _tick() -> None:
            if self._stopped:
                return
            self.flush()
            if not self._stopped:
                self._timer = threading.Timer(self._flush_interval, _tick)
                self._timer.daemon = True
                self._timer.start()

        self._timer = threading.Timer(self._flush_interval, _tick)
        self._timer.daemon = True
        self._timer.start()

    def stop(self) -> None:
        """Cancel the periodic timer and do a final flush."""
        self._stopped = True
        timer = self._timer
        if timer is not None:
            timer.cancel()
            self._timer = None
        self.flush()
