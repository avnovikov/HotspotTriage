"""Per-commit block snapshots for MCP revision comparison (``revisions.pkl``).

Stored under ``<repo>/.hotspottriage/cache/revisions.pkl`` alongside
``blocks.pkl``.  Snapshots are **content-addressed**: rows are grouped by
``(file_path, blob_sha)`` so unchanged files across commits deduplicate on disk.

Each manifest maps a **full commit SHA** (from ``git rev-parse HEAD`` at record
time) to the subset of ``path → blob_sha`` for files that appeared in that
analyze run (see :func:`file_blob_shas`).  Rows that are not normal
``file::symbol`` blocks (synthetics, directory aggregates, etc.) live in
per-commit ``extras``.
"""
from __future__ import annotations

import logging
import os
import pickle
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from hotspottriage import cache as _cache
from hotspottriage.block_churn import file_blob_shas
from hotspottriage.path_utils import sanitize_log_value
from hotspottriage.statistic_row import Statistic

logger = logging.getLogger(__name__)

REVISION_CACHE_VERSION = 1
_REVISION_CACHE_FILENAME = "revisions.pkl"


class SnapshotNotFoundError(LookupError):
    """Raised when a requested revision has no recorded snapshot."""

    def __init__(self, rev: str, resolved_sha: str) -> None:
        self.rev = rev
        self.resolved_sha = resolved_sha
        super().__init__(
            f"no cached snapshot for {resolved_sha} (from rev {rev!r}); "
            "run MCP analyze on a checkout at that commit first and use the returned "
            "`head_sha` so HotspotTriage can record metrics."
        )


def revisions_cache_path(repo: Path) -> Path:
    return _cache.cache_path_for(repo) / _REVISION_CACHE_FILENAME


def head_commit_sha(repo: Path) -> str:
    """Return the full object name of ``HEAD`` for *repo*."""
    proc = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    lines = proc.stdout.strip().splitlines()
    if not lines:
        raise ValueError("git rev-parse HEAD returned empty output")
    sha = lines[0].strip()
    if not sha:
        raise ValueError("git rev-parse HEAD returned empty output")
    return sha


def resolve_commit_sha(repo: Path, rev: str) -> str:
    """Resolve *rev* to a full 40-hex commit object name (``rev-parse``)."""
    token = rev.strip()
    if not token:
        raise ValueError("revision must be non-empty")
    spec = f"{token}^" + "{commit}"
    proc = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", spec],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise ValueError(
            f"invalid git revision {rev!r}: {err}" if err else f"invalid git revision {rev!r}"
        )
    lines = proc.stdout.strip().splitlines()
    if not lines:
        raise ValueError(f"git rev-parse returned empty output for {rev!r}")
    return lines[0].strip()


def statistic_from_dict(d: dict[str, Any]) -> Statistic:
    """Rebuild a :class:`Statistic` from :meth:`Statistic.as_dict` output."""
    names = set(Statistic.__dataclass_fields__)
    return Statistic(**{k: d[k] for k in d if k in names})


def clear_revision_cache_file(repo: Path) -> bool:
    """Delete ``revisions.pkl`` if it exists; return whether a file was removed."""
    p = revisions_cache_path(repo)
    if p.exists():
        p.unlink()
        return True
    return False


class RevisionCacheManager:
    """Load / mutate / persist the revision snapshot store for one repository."""

    def __init__(self, repo: Path) -> None:
        self._repo = repo.resolve()
        self._manifests: dict[str, dict[str, str]] = {}
        self._blob_blocks: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self._extras: dict[str, list[dict[str, Any]]] = {}
        self._path = revisions_cache_path(self._repo)
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        if not self._path.exists():
            return
        try:
            with open(self._path, "rb") as f:
                raw = pickle.load(f)
        except (OSError, pickle.UnpicklingError, EOFError):
            logger.info(
                "Unreadable revision cache at %s — starting fresh",
                sanitize_log_value(str(self._path)),
            )
            return
        if not isinstance(raw, dict) or raw.get("__cache_version") != REVISION_CACHE_VERSION:
            logger.info(
                "Revision cache version mismatch at %s — starting fresh",
                sanitize_log_value(str(self._path)),
            )
            return
        obj = raw.get("obj")
        if not isinstance(obj, dict):
            return
        man = obj.get("manifests")
        bb = obj.get("blob_blocks")
        ex = obj.get("extras")
        if isinstance(man, dict):
            self._manifests = {
                str(k): {str(pk): str(pv) for pk, pv in v.items()}
                for k, v in man.items()
                if isinstance(v, dict)
            }
        if isinstance(bb, dict):
            for k, v in bb.items():
                if (
                    isinstance(k, tuple)
                    and len(k) == 2
                    and isinstance(v, list)
                    and all(isinstance(x, dict) for x in v)
                ):
                    self._blob_blocks[(str(k[0]), str(k[1]))] = list(v)
        if isinstance(ex, dict):
            self._extras = {
                str(k): [row for row in v if isinstance(row, dict)]
                for k, v in ex.items()
                if isinstance(v, list)
            }

    def flush(self) -> None:
        """Atomically write manifests + blob_blocks + extras to disk."""
        envelope = {
            "__cache_version": REVISION_CACHE_VERSION,
            "obj": {
                "manifests": self._manifests,
                "blob_blocks": self._blob_blocks,
                "extras": self._extras,
            },
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            dir=self._path.parent, prefix=".revisions-", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "wb") as f:
                pickle.dump(envelope, f)
            os.replace(tmp, self._path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def list_snapshots(self) -> list[str]:
        return sorted(self._manifests.keys())

    def has_snapshot(self, rev: str) -> bool:
        token = rev.strip()
        if token in self._manifests:
            return True
        sha = resolve_commit_sha(self._repo, rev)
        return sha in self._manifests

    def record_snapshot(self, rows: list[Any]) -> str:
        """Persist *rows* for ``HEAD``; returns the recorded commit SHA."""
        commit = head_commit_sha(self._repo)
        full_tree = file_blob_shas(self._repo)
        paths_from_blocks: set[str] = set()
        for row in rows:
            p = str(getattr(row, "path", ""))
            if "::" not in p:
                continue
            fp = p.split("::", 1)[0]
            if fp.startswith("__"):
                continue
            paths_from_blocks.add(fp)

        manifest: dict[str, str] = {
            fp: full_tree[fp] for fp in paths_from_blocks if fp in full_tree
        }

        groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        extras: list[dict[str, Any]] = []
        for row in rows:
            d = row.as_dict() if hasattr(row, "as_dict") else dict(row)
            p = str(d.get("path", ""))
            if "::" in p:
                fp = p.split("::", 1)[0]
                if not fp.startswith("__"):
                    blob = manifest.get(fp)
                    if blob is not None:
                        groups[(fp, blob)].append(d)
                        continue
            extras.append(d)

        self._manifests[commit] = manifest
        self._extras[commit] = extras
        for key, lst in groups.items():
            self._blob_blocks[key] = lst

        self.flush()
        return commit

    def get_snapshot_statistics(self, rev: str) -> list[Statistic]:
        token = rev.strip()
        if token in self._manifests:
            sha = token
        else:
            sha = resolve_commit_sha(self._repo, rev)
        if sha not in self._manifests:
            raise SnapshotNotFoundError(rev, sha)
        manifest = self._manifests[sha]
        flat: list[dict[str, Any]] = []
        for fp in sorted(manifest.keys()):
            blob = manifest[fp]
            key = (fp, blob)
            rows = self._blob_blocks.get(key)
            if rows:
                flat.extend(rows)
        flat.extend(self._extras.get(sha, []))
        return [statistic_from_dict(d) for d in flat]
