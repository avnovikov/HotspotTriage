"""Timestamp tracking for cache validity and delta analysis.

Tracks when metrics were last computed and provides tools to:
- Detect stale cache (when code has changed since last analysis)
- Calculate deltas between cache versions
- Identify files that need re-analysis
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FileTimestamp:
    """Metadata for a file's analysis timestamp."""
    path: str
    last_commit_timestamp: int  # Unix timestamp of last commit touching this file
    analysis_timestamp: int     # Unix timestamp when analysis was performed
    blob_sha: str              # Git blob SHA at time of analysis


@dataclass(frozen=True)
class CacheMetadata:
    """Metadata about when the cache was generated."""
    generated_at: int  # Unix timestamp
    target: str       # Repository path
    filter: str | None
    score_metrics: list[str]
    python_version: str
    files: dict[str, FileTimestamp]  # path -> FileTimestamp


def get_file_last_commit_timestamp(repo: Path, file_path: str) -> int:
    """Get the Unix timestamp of the last commit touching a file.

    Args:
        repo: Repository root path
        file_path: Path to file relative to repo

    Returns:
        Unix timestamp of last commit, or 0 if file not found
    """
    try:
        import subprocess
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ct", "--", file_path],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return int(result.stdout.strip())
    except Exception:
        # Missing git binary, permission errors, or unexpected git output.
        pass
    return 0


def get_file_blob_sha(repo: Path, file_path: str) -> str:
    """Get the current blob SHA for a file.

    Args:
        repo: Repository root path
        file_path: Path to file relative to repo

    Returns:
        Git blob SHA, or empty string if not found
    """
    try:
        import subprocess
        result = subprocess.run(
            ["git", "hash-object", file_path],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        # Missing git binary, permission errors, or unexpected git output.
        pass
    return ""


def create_cache_metadata(
    repo: Path,
    files: list[str],
    filter_str: str | None = None,
    score_metrics: list[str] | None = None,
) -> CacheMetadata:
    """Create metadata for a cache generation.

    Args:
        repo: Repository root path
        files: List of analyzed files
        filter_str: Filter patterns used
        score_metrics: Metrics used for scoring

    Returns:
        CacheMetadata with timestamp and file info
    """
    import sys

    file_timestamps: dict[str, FileTimestamp] = {}
    for file_path in files:
        last_commit = get_file_last_commit_timestamp(repo, file_path)
        blob_sha = get_file_blob_sha(repo, file_path)
        file_timestamps[file_path] = FileTimestamp(
            path=file_path,
            last_commit_timestamp=last_commit,
            analysis_timestamp=int(datetime.now().timestamp()),
            blob_sha=blob_sha,
        )

    return CacheMetadata(
        generated_at=int(datetime.now().timestamp()),
        target=str(repo),
        filter=filter_str,
        score_metrics=score_metrics or [],
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}",
        files=file_timestamps,
    )


def is_cache_stale(
    repo: Path,
    metadata: CacheMetadata,
    stale_threshold_seconds: int = 3600,
) -> tuple[bool, list[str]]:
    """Check if cache is stale based on file modifications.

    Args:
        repo: Repository root path
        metadata: Cache metadata to check
        stale_threshold_seconds: Consider cache stale if last file change is within this duration

    Returns:
        (is_stale, list of files that have changed since analysis)
    """
    changed_files = []

    for file_path, cached_ts in metadata.files.items():
        # Get current commit timestamp
        current_commit_ts = get_file_last_commit_timestamp(repo, file_path)

        # If file has changed since analysis, it's stale
        if current_commit_ts > cached_ts.analysis_timestamp:
            changed_files.append(file_path)

    is_stale = len(changed_files) > 0
    return is_stale, changed_files


def estimate_delta_impact(
    repo: Path,
    old_metadata: CacheMetadata,
    new_metadata: CacheMetadata,
) -> dict[str, Any]:
    """Estimate the impact of changes between two cache versions.

    Args:
        repo: Repository root path
        old_metadata: Previous cache metadata
        new_metadata: Current cache metadata

    Returns:
        Dictionary with delta analysis:
        - files_changed: List of files that changed
        - files_added: List of new files
        - files_deleted: List of removed files
        - total_changes: Number of changed files
        - change_percentage: Percent of files changed
    """
    old_files = set(old_metadata.files.keys())
    new_files = set(new_metadata.files.keys())

    files_changed = []
    for file_path in old_files & new_files:
        old_ts = old_metadata.files[file_path]
        new_ts = new_metadata.files[file_path]
        # File changed if blob SHA differs
        if old_ts.blob_sha != new_ts.blob_sha:
            files_changed.append(file_path)

    files_added = list(new_files - old_files)
    files_deleted = list(old_files - new_files)

    total_files = len(new_files) if new_files else 1
    change_percentage = (len(files_changed) / total_files * 100) if total_files > 0 else 0

    return {
        "files_changed": files_changed,
        "files_added": files_added,
        "files_deleted": files_deleted,
        "total_changes": len(files_changed),
        "change_percentage": round(change_percentage, 2),
        "analysis_age_seconds": int(datetime.now().timestamp()) - new_metadata.generated_at,
    }


def save_metadata(cache_dir: Path, metadata: CacheMetadata) -> Path:
    """Save cache metadata to disk.

    Args:
        cache_dir: Cache directory
        metadata: Metadata to save

    Returns:
        Path to metadata file
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    metadata_file = cache_dir / "metadata.json"

    # Convert dataclasses to dicts for JSON serialization
    data = {
        "generated_at": metadata.generated_at,
        "target": metadata.target,
        "filter": metadata.filter,
        "score_metrics": metadata.score_metrics,
        "python_version": metadata.python_version,
        "files": {
            path: asdict(ts)
            for path, ts in metadata.files.items()
        },
    }

    metadata_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return metadata_file


def load_metadata(cache_dir: Path) -> CacheMetadata | None:
    """Load cache metadata from disk.

    Args:
        cache_dir: Cache directory

    Returns:
        CacheMetadata if found, None otherwise
    """
    metadata_file = cache_dir / "metadata.json"
    if not metadata_file.exists():
        return None

    try:
        data = json.loads(metadata_file.read_text(encoding="utf-8"))
        files = {
            path: FileTimestamp(**ts_dict)
            for path, ts_dict in data.get("files", {}).items()
        }
        return CacheMetadata(
            generated_at=data["generated_at"],
            target=data["target"],
            filter=data.get("filter"),
            score_metrics=data.get("score_metrics", []),
            python_version=data.get("python_version", ""),
            files=files,
        )
    except Exception as e:
        raise ValueError(f"Failed to load cache metadata: {e}")


def format_timestamp_readable(timestamp: int) -> str:
    """Format Unix timestamp as readable string.

    Args:
        timestamp: Unix timestamp

    Returns:
        Human-readable datetime string
    """
    from datetime import datetime, timezone
    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def int_timestamp_now() -> int:
    """Get current Unix timestamp as integer.

    Returns:
        Unix timestamp
    """
    return int(datetime.now().timestamp())


def age_seconds(timestamp: int) -> int:
    """Calculate seconds elapsed since a timestamp.

    Args:
        timestamp: Unix timestamp

    Returns:
        Seconds elapsed
    """
    return int_timestamp_now() - timestamp


def save_metadata_simple(cache_dir: Path, metadata: dict) -> None:
    """Save simple metadata dict to metadata.json.

    Args:
        cache_dir: Cache directory
        metadata: Metadata dict to save
    """
    base = Path(cache_dir).resolve()
    base.mkdir(parents=True, exist_ok=True)
    metadata_file = (base / "metadata.json").resolve()
    if not metadata_file.is_relative_to(base):
        raise ValueError(f"refusing to write metadata outside cache dir: {metadata_file}")
    metadata_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def load_metadata_simple(cache_dir: Path) -> dict | None:
    """Load simple metadata from metadata.json.

    Args:
        cache_dir: Cache directory

    Returns:
        Metadata dict, or None if not found
    """
    base = Path(cache_dir).resolve()
    metadata_file = (base / "metadata.json").resolve()
    if not metadata_file.is_relative_to(base):
        return None
    if not metadata_file.exists():
        return None
    try:
        return json.loads(metadata_file.read_text(encoding="utf-8"))
    except Exception:
        return None
