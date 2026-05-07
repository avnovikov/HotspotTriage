from pathlib import Path

import pytest

from hotspottriage import block_churn
from tests.fixtures.build_block_repo import build_block_repo


def test_file_blob_shas_lists_tracked_files(tmp_path: Path):
    repo = build_block_repo(tmp_path / "r")
    shas = block_churn.file_blob_shas(repo)
    assert "mod.py" in shas
    assert len(shas["mod.py"]) == 40  # SHA-1 hex


def test_compute_one_returns_positive_for_changed_block(tmp_path: Path):
    """Foo.bar was rewritten between v1 and v2 → its line range churns."""
    repo = build_block_repo(tmp_path / "r")
    n = block_churn.compute_one(repo, "mod.py", 6, 12, since=None, until=None)
    assert n > 0


def test_cache_round_trip(tmp_path: Path):
    """Two compute_many calls — second one should hit cache (no work)."""
    repo = build_block_repo(tmp_path / "r")
    shas = block_churn.file_blob_shas(repo)
    requests = [("mod.py", shas["mod.py"], 6, 12)]

    out_a = block_churn.compute_many(repo, requests, None, None)

    # Build previous_rows from first run so second run can reuse churn.
    previous_rows = {
        "mod.py::block": {
            "_blob_sha": shas["mod.py"],
            "_start": 6,
            "_end": 12,
            "churn": out_a[("mod.py", 6, 12)],
            "path": "mod.py::block",
        }
    }

    # Patch compute_one to raise — second invocation must not call it.
    old_compute_one = block_churn.compute_one
    try:
        block_churn.compute_one = lambda *a, **kw: (_ for _ in ()).throw(
            AssertionError("cache miss — compute_one should not be called")
        )
        out_b = block_churn.compute_many(
            repo, requests, None, None, previous_rows=previous_rows
        )
        assert out_a == out_b
    finally:
        block_churn.compute_one = old_compute_one


def test_cache_invalidates_when_file_changes(tmp_path: Path):
    """Mutating the file changes its blob SHA, so old cached entries miss."""
    repo = build_block_repo(tmp_path / "r")

    shas_before = block_churn.file_blob_shas(repo)
    out_a = block_churn.compute_many(
        repo, [("mod.py", shas_before["mod.py"], 6, 12)], None, None
    )

    previous_rows = {
        "mod.py::block": {
            "_blob_sha": shas_before["mod.py"],
            "_start": 6,
            "_end": 12,
            "churn": out_a[("mod.py", 6, 12)],
            "path": "mod.py::block",
        }
    }

    # New commit changes the blob SHA.
    (repo / "mod.py").write_text((repo / "mod.py").read_text() + "\n# trailing\n")
    import subprocess
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-am", "tweak"],
        check=True, capture_output=True,
    )
    shas_after = block_churn.file_blob_shas(repo)
    assert shas_after["mod.py"] != shas_before["mod.py"]

    # With new SHA, the previous row shouldn't match → must recompute.
    out_b = block_churn.compute_many(
        repo,
        [("mod.py", shas_after["mod.py"], 6, 12)],
        None,
        None,
        previous_rows=previous_rows,
    )
    assert ("mod.py", 6, 12) in out_b
