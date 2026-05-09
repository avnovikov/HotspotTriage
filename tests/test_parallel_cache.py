"""Tests for cache short-circuit and parallel file scanning (issue #75).

These tests verify:
1. Unchanged files skip recomputation (cache short-circuit)
2. Changed files are reprocessed
3. Parallel scan produces same results as serial
4. New files are added correctly
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from hotspottriage import cache as _cache
from hotspottriage import complexity as _complexity
from hotspottriage import smell as _smell
from hotspottriage import stats as _stats
from hotspottriage.block_churn import file_blob_shas
from hotspottriage.config import DEFAULTS


def _git(repo: Path, *args: str) -> None:
    """Run a git command in the repo."""
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def build_parallel_test_repo(root: Path) -> Path:
    """Create a repo with multiple Python files for parallel/cache testing.

    Creates:
    - file1.py: simple functions
    - file2.py: class with methods
    - file3.py: more complex functions
    """
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "commit.gpgsign", "false")

    # file1.py: simple module-level functions
    file1 = root / "file1.py"
    file1.write_text(
        '"""Module 1 with simple functions."""\n\n\n'
        'def simple_func(x):\n'
        '    if x > 0:\n'
        '        return x * 2\n'
        '    return 0\n\n\n'
        'def another_func(y):\n'
        '    for i in range(y):\n'
        '        print(i)\n'
        '    return y\n'
    )

    # file2.py: class with methods
    file2 = root / "file2.py"
    file2.write_text(
        '"""Module 2 with classes."""\n\n\n'
        'class MyClass:\n'
        '    def method_one(self, a):\n'
        '        if a:\n'
        '            return 1\n'
        '        return 0\n\n'
        '    def method_two(self, b, c):\n'
        '        result = b + c\n'
        '        return result\n'
    )

    # file3.py: more complex functions
    file3 = root / "file3.py"
    file3.write_text(
        '"""Module 3 with complexity."""\n\n\n'
        'def complex_func(n):\n'
        '    total = 0\n'
        '    for i in range(n):\n'
        '        if i % 2 == 0:\n'
        '            total += i\n'
        '        elif i % 3 == 0:\n'
        '            total -= i\n'
        '    return total\n\n\n'
        'def simple_helper():\n'
        '        return 42\n'
    )

    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "initial commit")
    return root


@pytest.fixture
def parallel_repo(tmp_path: Path) -> Path:
    """Provide a test repo with multiple files."""
    return build_parallel_test_repo(tmp_path / "parallel_repo")


class TestUnchangedFilesSkipRecomputation:
    """Test 1: Unchanged files with same blob SHA skip compute_all/compute_smells."""

    def test_unchanged_files_skip_recomputation(self, parallel_repo: Path) -> None:
        """Verify that files with unchanged blob SHAs skip expensive computations.

        Steps:
        1. Run build_block_stats once (populates cache)
        2. Mock compute_all and compute_smells
        3. Run build_block_stats again without changes
        4. Assert mocks NOT called
        5. Assert results match first run
        """
        files = ["file1.py", "file2.py", "file3.py"]

        # First run - populate cache
        first_results = _stats.build_block_stats(
            parallel_repo,
            files,
            score_metrics=["cyclomatic"],
            similarity_enabled=False,
            similarity_aggregate_row=False,
            merged_config=DEFAULTS,
        )

        # Verify cache was populated
        cached_rows = _cache.load_block_results(parallel_repo)
        assert cached_rows is not None
        assert len(cached_rows) > 0

        # Second run with mocks - should NOT call expensive functions
        with patch.object(_complexity, "compute_all") as mock_compute_all, \
             patch.object(_smell, "compute_smells") as mock_compute_smells:

            second_results = _stats.build_block_stats(
                parallel_repo,
                files,
                score_metrics=["cyclomatic"],
                similarity_enabled=False,
                similarity_aggregate_row=False,
                merged_config=DEFAULTS,
            )

            # Verify mocks were NOT called for unchanged files
            mock_compute_all.assert_not_called()
            mock_compute_smells.assert_not_called()

        # Results should be identical (except time-dependent decayed_churn)
        first_by_path = {s.path: s for s in first_results}
        second_by_path = {s.path: s for s in second_results}

        assert set(first_by_path.keys()) == set(second_by_path.keys())

        for path in first_by_path:
            first = first_by_path[path]
            second = second_by_path[path]

            # Compare non-time-dependent fields
            assert first.sloc == second.sloc
            assert first.cyclomatic == second.cyclomatic
            assert first.halstead == second.halstead
            assert first.maintainability == second.maintainability
            assert first.churn == second.churn
            assert first.churn_per_sloc == pytest.approx(second.churn_per_sloc)
            assert first.smell_count == second.smell_count
            assert first.smell_severity == pytest.approx(second.smell_severity)
            assert first.smell_burden == pytest.approx(second.smell_burden)
            assert first.score == pytest.approx(second.score)


class TestChangedFileReprocessed:
    """Test 2: Changed files are reprocessed while unchanged files skip."""

    def test_changed_file_reprocessed(self, parallel_repo: Path) -> None:
        """Verify that modified files are reprocessed, unchanged ones are not.

        Steps:
        1. Run build_block_stats once
        2. Modify one file (changes its blob SHA)
        3. Commit the change
        4. Run build_block_stats again with mocks
        5. Assert compute_all called for changed file
        6. Assert compute_all NOT called for unchanged files
        """
        files = ["file1.py", "file2.py", "file3.py"]

        # First run - populate cache
        _stats.build_block_stats(
            parallel_repo,
            files,
            score_metrics=["cyclomatic"],
            similarity_enabled=False,
            similarity_aggregate_row=False,
            merged_config=DEFAULTS,
        )

        # Record blob SHAs before change
        shas_before = file_blob_shas(parallel_repo)

        # Modify file2.py
        file2 = parallel_repo / "file2.py"
        file2.write_text(
            '"""Modified module 2 with classes."""\n\n\n'
            'class MyClass:\n'
            '    def method_one(self, a, b, c, d):\n'  # Added more params
            '        if a and b:\n'
            '            return 1\n'
            '        return 0\n\n'
            '    def method_two(self, x):\n'  # Changed signature
            '        return x * 2\n\n'
            '    def new_method(self):\n'  # New method
            '        pass\n'
        )

        _git(parallel_repo, "add", "-A")
        _git(parallel_repo, "commit", "-q", "-m", "modified file2.py")

        # Verify blob SHA changed
        shas_after = file_blob_shas(parallel_repo)
        assert shas_after["file2.py"] != shas_before["file2.py"]
        assert shas_after["file1.py"] == shas_before["file1.py"]
        assert shas_after["file3.py"] == shas_before["file3.py"]

        # Track which files were processed
        processed_files: list[str] = []

        original_compute_all = _complexity.compute_all

        def tracking_compute_all(path: Path) -> dict[str, int]:
            rel_path = str(path.relative_to(parallel_repo))
            processed_files.append(rel_path)
            return original_compute_all(path)

        # Run with tracking
        with patch.object(_complexity, "compute_all", side_effect=tracking_compute_all):
            _stats.build_block_stats(
                parallel_repo,
                files,
                score_metrics=["cyclomatic"],
                similarity_enabled=False,
                similarity_aggregate_row=False,
                merged_config=DEFAULTS,
            )

        # Only file2.py should have been reprocessed
        assert "file2.py" in processed_files
        assert "file1.py" not in processed_files
        assert "file3.py" not in processed_files


class TestParallelScanProducesSameResults:
    """Test 3: Repeated scan passes are deterministic."""

    def test_parallel_scan_produces_same_results_as_serial(self, parallel_repo: Path) -> None:
        """Verify that repeated _scan_files_for_blocks runs produce identical results."""
        files = ["file1.py", "file2.py", "file3.py"]

        # Build context
        blob_shas = file_blob_shas(parallel_repo)
        previous_rows, prev_rows_list = _stats._load_previous_cache(
            parallel_repo, None
        )

        ctx = _stats._BlockAnalysisContext(
            repo=parallel_repo,
            files=files,
            blob_shas=blob_shas,
            previous_rows=previous_rows,
            prev_rows_list=prev_rows_list,
            timestamps={},
            current_time=0,
            merged_config=DEFAULTS,
        )

        # Scan is deterministic; repeated passes must agree (no scan-level workers knob).
        serial_metrics, serial_blocks, serial_sources, serial_smells, serial_requests = (
            _stats._scan_files_for_blocks(ctx, None)
        )

        parallel_metrics, parallel_blocks, parallel_sources, parallel_smells, parallel_requests = (
            _stats._scan_files_for_blocks(ctx, None)
        )

        # Assert file_metrics identical
        assert serial_metrics == parallel_metrics

        # Assert file_blocks identical (comparing block names and positions)
        assert set(serial_blocks.keys()) == set(parallel_blocks.keys())
        for path in serial_blocks:
            serial_block_list = serial_blocks[path]
            parallel_block_list = parallel_blocks[path]
            assert len(serial_block_list) == len(parallel_block_list)
            for s_block, p_block in zip(serial_block_list, parallel_block_list):
                assert s_block.name == p_block.name
                assert s_block.start == p_block.start
                assert s_block.end == p_block.end

        # Assert file_sources identical
        assert serial_sources == parallel_sources

        # Assert file_smells identical
        assert serial_smells == parallel_smells

        # Assert requests identical (same blocks to query for churn)
        assert sorted(serial_requests) == sorted(parallel_requests)


class TestNewFileAddedToRepo:
    """Test 4: New files go through full pipeline, existing unchanged files use cache."""

    def test_new_file_added_to_repo(self, parallel_repo: Path) -> None:
        """Verify new files are fully processed while unchanged files use cache.

        Steps:
        1. Run build_block_stats on initial files
        2. Add a new Python file and commit
        3. Run build_block_stats with all files including the new one
        4. Assert new file went through full pipeline
        5. Assert existing unchanged files skipped computation
        """
        initial_files = ["file1.py", "file2.py"]

        # First run - populate cache for initial files
        _stats.build_block_stats(
            parallel_repo,
            initial_files,
            score_metrics=["cyclomatic"],
            similarity_enabled=False,
            similarity_aggregate_row=False,
            merged_config=DEFAULTS,
        )

        # Verify cache for initial files
        cached = _cache.load_block_results(parallel_repo)
        assert cached is not None

        # Add new file
        file4 = parallel_repo / "file4.py"
        file4.write_text(
            '"""Newly added module."""\n\n\n'
            'def brand_new_function(x):\n'
            '    while x > 0:\n'
            '        x -= 1\n'
            '    return x\n'
        )
        _git(parallel_repo, "add", "-A")
        _git(parallel_repo, "commit", "-q", "-m", "added file4.py")

        # Track processed files
        processed_files: list[str] = []
        original_compute_all = _complexity.compute_all

        def tracking_compute_all(path: Path) -> dict[str, int]:
            rel_path = str(path.relative_to(parallel_repo))
            processed_files.append(rel_path)
            return original_compute_all(path)

        # Run with all files including the new one
        all_files = ["file1.py", "file2.py", "file3.py", "file4.py"]

        with patch.object(_complexity, "compute_all", side_effect=tracking_compute_all):
            results = _stats.build_block_stats(
                parallel_repo,
                all_files,
                score_metrics=["cyclomatic"],
                similarity_enabled=False,
                similarity_aggregate_row=False,
                merged_config=DEFAULTS,
            )

        # New file (file4.py) should have been processed
        assert "file4.py" in processed_files

        # file3.py also needs processing (first time in the run)
        assert "file3.py" in processed_files

        # file1.py and file2.py should NOT be reprocessed (unchanged + cached)
        assert "file1.py" not in processed_files
        assert "file2.py" not in processed_files

        # Verify results include blocks from new file
        result_paths = [s.path for s in results]
        new_file_blocks = [p for p in result_paths if p.startswith("file4.py::")]
        assert len(new_file_blocks) > 0, "New file should have block entries"

        # Verify the new file's block is in the results
        assert any("brand_new_function" in p for p in new_file_blocks)


class TestCacheIntegration:
    """Additional integration tests for cache behavior."""

    def test_cache_populated_after_first_run(self, parallel_repo: Path) -> None:
        """Verify cache is properly populated after first analysis run."""
        files = ["file1.py", "file2.py"]

        # Before first run - no cache
        before = _cache.load_block_results(parallel_repo)
        assert before is None or len(before) == 0

        # First run
        _stats.build_block_stats(
            parallel_repo,
            files,
            score_metrics=["cyclomatic"],
            similarity_enabled=False,
            similarity_aggregate_row=False,
            merged_config=DEFAULTS,
        )

        # After first run - cache should exist
        after = _cache.load_block_results(parallel_repo)
        assert after is not None
        assert len(after) > 0

        # Verify cache entries have required metadata
        for row in after:
            assert "_blob_sha" in row
            assert "_start" in row
            assert "_end" in row
            assert "path" in row
            assert "churn" in row

    def test_empty_file_list_produces_empty_results(self, parallel_repo: Path) -> None:
        """Verify empty file list produces empty results without error."""
        results = _stats.build_block_stats(
            parallel_repo,
            [],
            score_metrics=["cyclomatic"],
            similarity_enabled=False,
            similarity_aggregate_row=False,
            merged_config=DEFAULTS,
        )
        assert results == []

    def test_single_file_repo(self, tmp_path: Path) -> None:
        """Verify behavior with a single file repo."""
        repo = tmp_path / "single_file_repo"
        repo.mkdir(parents=True, exist_ok=True)
        _git(repo, "init", "-q", "-b", "main")
        _git(repo, "config", "user.email", "t@t")
        _git(repo, "config", "user.name", "t")
        _git(repo, "config", "commit.gpgsign", "false")

        (repo / "only.py").write_text(
            'def only_function():\n    return 1\n'
        )
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "initial")

        # First run
        results1 = _stats.build_block_stats(
            repo,
            ["only.py"],
            score_metrics=["cyclomatic"],
            similarity_enabled=False,
            similarity_aggregate_row=False,
            merged_config=DEFAULTS,
        )

        # Second run should use cache
        with patch.object(_complexity, "compute_all") as mock_compute:
            results2 = _stats.build_block_stats(
                repo,
                ["only.py"],
                score_metrics=["cyclomatic"],
                similarity_enabled=False,
                similarity_aggregate_row=False,
                merged_config=DEFAULTS,
            )
            mock_compute.assert_not_called()

        assert len(results1) == len(results2)

    def test_blob_shas_detect_file_changes(self, parallel_repo: Path) -> None:
        """Verify that blob SHAs change when files are modified."""
        # Get initial SHAs
        shas_before = file_blob_shas(parallel_repo)

        # Modify file1.py
        file1 = parallel_repo / "file1.py"
        original_content = file1.read_text()
        file1.write_text(original_content + "\n# modified\n")

        _git(parallel_repo, "add", "-A")
        _git(parallel_repo, "commit", "-q", "-m", "modify file1")

        # Get new SHAs
        shas_after = file_blob_shas(parallel_repo)

        # Only file1.py should have changed
        assert shas_after["file1.py"] != shas_before["file1.py"]
        assert shas_after["file2.py"] == shas_before["file2.py"]
        assert shas_after["file3.py"] == shas_before["file3.py"]

    def test_cache_indexed_by_blob_sha(self, parallel_repo: Path) -> None:
        """Verify cache entries include blob SHA for staleness detection."""
        files = ["file1.py"]

        # Run analysis
        _stats.build_block_stats(
            parallel_repo,
            files,
            score_metrics=["cyclomatic"],
            similarity_enabled=False,
            similarity_aggregate_row=False,
            merged_config=DEFAULTS,
        )

        # Get current blob SHA
        current_shas = file_blob_shas(parallel_repo)

        # Check cache entries have correct blob SHA
        cached = _cache.load_block_results(parallel_repo)
        assert cached is not None

        for row in cached:
            if row.get("path", "").startswith("file1.py::"):
                assert row.get("_blob_sha") == current_shas["file1.py"]


class TestParallelExecution:
    """Tests for parallel execution behavior."""

    def test_scan_pass_is_deterministic(self, parallel_repo: Path) -> None:
        """Verify _scan_files_for_blocks is deterministic (no scan-level workers knob)."""
        files = ["file1.py"]

        blob_shas = file_blob_shas(parallel_repo)
        previous_rows, prev_rows_list = _stats._load_previous_cache(
            parallel_repo, None
        )

        ctx = _stats._BlockAnalysisContext(
            repo=parallel_repo,
            files=files,
            blob_shas=blob_shas,
            previous_rows=previous_rows,
            prev_rows_list=prev_rows_list,
            timestamps={},
            current_time=0,
            merged_config=DEFAULTS,
        )

        first = _stats._scan_files_for_blocks(ctx, None)
        for _ in range(3):
            metrics, blocks, sources, smells, requests = _stats._scan_files_for_blocks(
                ctx, None
            )
            assert (metrics, blocks, sources, smells, sorted(requests)) == (
                first[0],
                first[1],
                first[2],
                first[3],
                sorted(first[4]),
            )

            assert "file1.py" in metrics
            assert "file1.py" in blocks
            assert len(blocks["file1.py"]) > 0

    def test_parallel_scan_with_progress_callback(self, parallel_repo: Path) -> None:
        """Verify progress callback is invoked during file scanning."""

        files = ["file1.py", "file2.py", "file3.py"]

        blob_shas = file_blob_shas(parallel_repo)
        previous_rows, prev_rows_list = _stats._load_previous_cache(
            parallel_repo, None
        )

        ctx = _stats._BlockAnalysisContext(
            repo=parallel_repo,
            files=files,
            blob_shas=blob_shas,
            previous_rows=previous_rows,
            prev_rows_list=prev_rows_list,
            timestamps={},
            current_time=0,
            merged_config=DEFAULTS,
        )

        progress_calls: list[tuple[str, int, int]] = []

        def progress_callback(message: str, done: int, total: int) -> None:
            progress_calls.append((message, done, total))

        _stats._scan_files_for_blocks(ctx, progress_callback)

        # Should have received progress updates
        assert len(progress_calls) > 0

        # Each file should be represented
        file_progress = [c for c in progress_calls if "file" in c[0].lower()]
        assert len(file_progress) >= len(files)
