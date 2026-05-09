"""Tests for timestamp tracking functionality."""
from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from hotspottriage import timestamps


class TestTimestampHelpers:
    """Test basic timestamp utility functions."""

    def test_int_timestamp_now(self):
        """int_timestamp_now returns current Unix timestamp."""
        before = int(datetime.now().timestamp())
        ts = timestamps.int_timestamp_now()
        after = int(datetime.now().timestamp())
        assert before <= ts <= after

    def test_age_seconds(self):
        """age_seconds calculates seconds elapsed correctly."""
        now = timestamps.int_timestamp_now()
        # Simulate a timestamp from ~2 seconds ago
        old_ts = now - 2
        age = timestamps.age_seconds(old_ts)
        assert age >= 2  # At least 2 seconds

    def test_format_timestamp_readable(self):
        """format_timestamp_readable returns ISO-like string."""
        ts = 1609459200  # 2021-01-01 00:00:00 UTC
        result = timestamps.format_timestamp_readable(ts)
        assert "2021-01-01" in result
        assert "UTC" in result


class TestFileTimestamp:
    """Test FileTimestamp dataclass."""

    def test_file_timestamp_creation(self):
        """FileTimestamp can be created and accessed."""
        ft = timestamps.FileTimestamp(
            path="src/main.py",
            last_commit_timestamp=1000,
            analysis_timestamp=2000,
            blob_sha="abc123",
        )
        assert ft.path == "src/main.py"
        assert ft.last_commit_timestamp == 1000
        assert ft.analysis_timestamp == 2000
        assert ft.blob_sha == "abc123"

    def test_file_timestamp_frozen(self):
        """FileTimestamp is frozen and immutable."""
        ft = timestamps.FileTimestamp(
            path="src/main.py",
            last_commit_timestamp=1000,
            analysis_timestamp=2000,
            blob_sha="abc123",
        )
        with pytest.raises(AttributeError):
            ft.path = "other.py"


class TestCacheMetadata:
    """Test CacheMetadata dataclass."""

    def test_cache_metadata_creation(self):
        """CacheMetadata can be created with file timestamps."""
        files = {
            "src/main.py": timestamps.FileTimestamp(
                path="src/main.py",
                last_commit_timestamp=1000,
                analysis_timestamp=2000,
                blob_sha="abc123",
            ),
        }
        cm = timestamps.CacheMetadata(
            generated_at=2000,
            target="/repo",
            filter="*.py",
            score_metrics=["cyclomatic", "churn"],
            python_version="3.10",
            files=files,
        )
        assert cm.generated_at == 2000
        assert cm.target == "/repo"
        assert len(cm.files) == 1


class TestMetadataPersistence:
    """Test saving and loading metadata."""

    def test_save_and_load_metadata_simple(self):
        """save_metadata_simple and load_metadata_simple round-trip data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            metadata = {
                "generated_at": 1000,
                "entry_count": 42,
                "version": 1,
            }
            timestamps.save_metadata_simple(cache_dir, metadata)

            loaded = timestamps.load_metadata_simple(cache_dir)
            assert loaded == metadata

    def test_save_metadata_simple_creates_directory(self):
        """save_metadata_simple creates directory if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "nested" / "path"
            metadata = {"generated_at": 1000}
            timestamps.save_metadata_simple(cache_dir, metadata)
            assert cache_dir.exists()
            assert (cache_dir / "metadata.json").exists()

    def test_load_metadata_simple_missing_file(self):
        """load_metadata_simple returns None if metadata.json doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            result = timestamps.load_metadata_simple(cache_dir)
            assert result is None

    def test_load_metadata_simple_corrupted_file(self):
        """load_metadata_simple returns None on JSON decode error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            metadata_file = cache_dir / "metadata.json"
            metadata_file.write_text("{ invalid json }")
            result = timestamps.load_metadata_simple(cache_dir)
            assert result is None

    def test_save_and_load_full_metadata(self):
        """save_metadata and load_metadata round-trip CacheMetadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            files = {
                "src/main.py": timestamps.FileTimestamp(
                    path="src/main.py",
                    last_commit_timestamp=1000,
                    analysis_timestamp=2000,
                    blob_sha="abc123",
                ),
            }
            cm = timestamps.CacheMetadata(
                generated_at=2000,
                target="/repo",
                filter="*.py",
                score_metrics=["cyclomatic", "churn"],
                python_version="3.10",
                files=files,
            )
            timestamps.save_metadata(cache_dir, cm)

            loaded = timestamps.load_metadata(cache_dir)
            assert loaded is not None
            assert loaded.generated_at == cm.generated_at
            assert loaded.target == cm.target
            assert len(loaded.files) == 1
            assert "src/main.py" in loaded.files


class TestCacheValidity:
    """Test cache staleness detection."""

    def test_is_cache_stale_unchanged(self, tmp_path):
        """is_cache_stale returns False when files haven't changed."""
        # Create metadata for a single file
        files = {
            "src/main.py": timestamps.FileTimestamp(
                path="src/main.py",
                last_commit_timestamp=1000,
                analysis_timestamp=2000,
                blob_sha="abc123",
            ),
        }
        metadata = timestamps.CacheMetadata(
            generated_at=2000,
            target=str(tmp_path),
            filter=None,
            score_metrics=[],
            python_version="3.10",
            files=files,
        )

        # Mock get_file_last_commit_timestamp to return same timestamp
        original = timestamps.get_file_last_commit_timestamp
        timestamps.get_file_last_commit_timestamp = lambda repo, path: 1000
        try:
            is_stale, changed = timestamps.is_cache_stale(tmp_path, metadata)
            assert not is_stale
            assert changed == []
        finally:
            timestamps.get_file_last_commit_timestamp = original

    def test_is_cache_stale_changed(self, tmp_path):
        """is_cache_stale returns True when files have changed."""
        files = {
            "src/main.py": timestamps.FileTimestamp(
                path="src/main.py",
                last_commit_timestamp=1000,
                analysis_timestamp=2000,
                blob_sha="abc123",
            ),
        }
        metadata = timestamps.CacheMetadata(
            generated_at=2000,
            target=str(tmp_path),
            filter=None,
            score_metrics=[],
            python_version="3.10",
            files=files,
        )

        # Mock to return newer timestamp
        original = timestamps.get_file_last_commit_timestamp
        timestamps.get_file_last_commit_timestamp = lambda repo, path: 3000
        try:
            is_stale, changed = timestamps.is_cache_stale(tmp_path, metadata)
            assert is_stale
            assert "src/main.py" in changed
        finally:
            timestamps.get_file_last_commit_timestamp = original


class TestDeltaAnalysis:
    """Test delta calculation between cache versions."""

    def test_estimate_delta_no_changes(self, tmp_path):
        """estimate_delta_impact reports no changes when files unchanged."""
        files = {
            "src/main.py": timestamps.FileTimestamp(
                path="src/main.py",
                last_commit_timestamp=1000,
                analysis_timestamp=2000,
                blob_sha="abc123",
            ),
        }
        old_meta = timestamps.CacheMetadata(
            generated_at=1000,
            target=str(tmp_path),
            filter=None,
            score_metrics=[],
            python_version="3.10",
            files=files,
        )
        new_meta = timestamps.CacheMetadata(
            generated_at=2000,
            target=str(tmp_path),
            filter=None,
            score_metrics=[],
            python_version="3.10",
            files=files,
        )
        delta = timestamps.estimate_delta_impact(tmp_path, old_meta, new_meta)
        assert delta["total_changes"] == 0
        assert delta["files_changed"] == []
        assert delta["files_added"] == []
        assert delta["files_deleted"] == []

    def test_estimate_delta_file_changed(self, tmp_path):
        """estimate_delta_impact detects blob SHA changes."""
        old_files = {
            "src/main.py": timestamps.FileTimestamp(
                path="src/main.py",
                last_commit_timestamp=1000,
                analysis_timestamp=2000,
                blob_sha="abc123",
            ),
        }
        new_files = {
            "src/main.py": timestamps.FileTimestamp(
                path="src/main.py",
                last_commit_timestamp=1000,
                analysis_timestamp=2000,
                blob_sha="xyz789",  # Changed
            ),
        }
        old_meta = timestamps.CacheMetadata(
            generated_at=1000,
            target=str(tmp_path),
            filter=None,
            score_metrics=[],
            python_version="3.10",
            files=old_files,
        )
        new_meta = timestamps.CacheMetadata(
            generated_at=2000,
            target=str(tmp_path),
            filter=None,
            score_metrics=[],
            python_version="3.10",
            files=new_files,
        )
        delta = timestamps.estimate_delta_impact(tmp_path, old_meta, new_meta)
        assert delta["total_changes"] == 1
        assert "src/main.py" in delta["files_changed"]

    def test_estimate_delta_file_added(self, tmp_path):
        """estimate_delta_impact detects added files."""
        old_files = {}
        new_files = {
            "src/main.py": timestamps.FileTimestamp(
                path="src/main.py",
                last_commit_timestamp=1000,
                analysis_timestamp=2000,
                blob_sha="abc123",
            ),
        }
        old_meta = timestamps.CacheMetadata(
            generated_at=1000,
            target=str(tmp_path),
            filter=None,
            score_metrics=[],
            python_version="3.10",
            files=old_files,
        )
        new_meta = timestamps.CacheMetadata(
            generated_at=2000,
            target=str(tmp_path),
            filter=None,
            score_metrics=[],
            python_version="3.10",
            files=new_files,
        )
        delta = timestamps.estimate_delta_impact(tmp_path, old_meta, new_meta)
        assert "src/main.py" in delta["files_added"]

    def test_estimate_delta_file_deleted(self, tmp_path):
        """estimate_delta_impact detects deleted files."""
        old_files = {
            "src/main.py": timestamps.FileTimestamp(
                path="src/main.py",
                last_commit_timestamp=1000,
                analysis_timestamp=2000,
                blob_sha="abc123",
            ),
        }
        new_files = {}
        old_meta = timestamps.CacheMetadata(
            generated_at=1000,
            target=str(tmp_path),
            filter=None,
            score_metrics=[],
            python_version="3.10",
            files=old_files,
        )
        new_meta = timestamps.CacheMetadata(
            generated_at=2000,
            target=str(tmp_path),
            filter=None,
            score_metrics=[],
            python_version="3.10",
            files=new_files,
        )
        delta = timestamps.estimate_delta_impact(tmp_path, old_meta, new_meta)
        assert "src/main.py" in delta["files_deleted"]

    def test_estimate_delta_change_percentage(self, tmp_path):
        """estimate_delta_impact calculates change percentage correctly."""
        old_files = {
            f"src/file{i}.py": timestamps.FileTimestamp(
                path=f"src/file{i}.py",
                last_commit_timestamp=1000,
                analysis_timestamp=2000,
                blob_sha="abc123",
            )
            for i in range(10)
        }
        new_files = {
            f"src/file{i}.py": timestamps.FileTimestamp(
                path=f"src/file{i}.py",
                last_commit_timestamp=1000,
                analysis_timestamp=2000,
                blob_sha="xyz789" if i < 2 else "abc123",  # 2 files changed
            )
            for i in range(10)
        }
        old_meta = timestamps.CacheMetadata(
            generated_at=1000,
            target=str(tmp_path),
            filter=None,
            score_metrics=[],
            python_version="3.10",
            files=old_files,
        )
        new_meta = timestamps.CacheMetadata(
            generated_at=2000,
            target=str(tmp_path),
            filter=None,
            score_metrics=[],
            python_version="3.10",
            files=new_files,
        )
        delta = timestamps.estimate_delta_impact(tmp_path, old_meta, new_meta)
        assert delta["total_changes"] == 2
        assert delta["change_percentage"] == 20.0  # 2/10 = 20%
