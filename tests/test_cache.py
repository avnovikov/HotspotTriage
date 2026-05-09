import concurrent.futures
import pickle
import threading
import time
from pathlib import Path

from hotspottriage.cache import (
    BlockCacheManager,
    CACHE_VERSION,
    cache_path_for,
    save_block_results,
    load_block_results,
    get_metadata,
    _CACHE_FILE,
)


# ── Legacy free-function tests ──────────────────────────────────────


def test_cache_path_in_project_hotspottriage(tmp_path: Path):
    p = cache_path_for(tmp_path / "myrepo")
    assert p == tmp_path / "myrepo" / ".hotspottriage" / "cache"


def test_cache_path_is_stable_for_same_repo(tmp_path: Path):
    a = cache_path_for(tmp_path / "myrepo")
    b = cache_path_for(tmp_path / "myrepo")
    assert a == b


def test_save_and_load_round_trip(tmp_path: Path):
    repo = tmp_path / "myrepo"
    rows = [
        {"path": "a.py::foo", "churn": 10, "_blob_sha": "abc", "_start": 1, "_end": 5},
        {"path": "a.py::bar", "churn": 20, "_blob_sha": "abc", "_start": 7, "_end": 12},
    ]
    save_block_results(repo, rows)
    loaded = load_block_results(repo)
    assert loaded == rows


def test_save_creates_cache_file(tmp_path: Path):
    repo = tmp_path / "myrepo"
    save_block_results(repo, [{"path": "x.py::f", "churn": 1}])
    pkl_path = cache_path_for(repo) / _CACHE_FILE
    assert pkl_path.exists()


def test_load_returns_none_when_no_cache(tmp_path: Path):
    assert load_block_results(tmp_path / "nope") is None


def test_load_returns_none_for_corrupt_file(tmp_path: Path):
    repo = tmp_path / "myrepo"
    cache_dir = cache_path_for(repo)
    cache_dir.mkdir(parents=True)
    (cache_dir / _CACHE_FILE).write_text("not pickle {{{")
    assert load_block_results(repo) is None


def test_save_writes_metadata(tmp_path: Path):
    repo = tmp_path / "myrepo"
    save_block_results(repo, [{"path": "x.py::f"}] * 3)
    meta = get_metadata(repo)
    assert meta is not None
    assert meta["entry_count"] == 3
    assert meta["version"] == CACHE_VERSION
    assert "generated_at" in meta


def test_versioned_envelope_rejects_old_format(tmp_path: Path):
    """A raw (non-envelope) pickle written by an older version is ignored."""
    repo = tmp_path / "myrepo"
    cache_dir = cache_path_for(repo)
    cache_dir.mkdir(parents=True)
    old_rows = [{"path": "a.py::f", "churn": 5}]
    with open(cache_dir / _CACHE_FILE, "wb") as f:
        pickle.dump(old_rows, f)
    loaded = load_block_results(repo)
    assert loaded is None


# ── BlockCacheManager tests ─────────────────────────────────────────


def test_manager_empty_repo(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    mgr = BlockCacheManager(repo, flush_interval_s=999)
    assert mgr.entry_count == 0
    assert mgr.generation == 0
    assert not mgr.modified
    mgr.stop()


def test_manager_put_rows_and_get(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    mgr = BlockCacheManager(repo, flush_interval_s=999)
    mgr.put_rows([
        {"path": "a.py::f", "churn": 10},
        {"path": "b.py::g", "churn": 20},
    ])
    assert mgr.entry_count == 2
    assert mgr.modified
    assert mgr.generation == 1
    assert mgr.get_row("a.py::f")["churn"] == 10
    assert mgr.get_row("missing") is None
    mgr.stop()


def test_manager_put_row_single(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    mgr = BlockCacheManager(repo, flush_interval_s=999)
    mgr.put_row({"path": "x.py::h", "churn": 7})
    assert mgr.entry_count == 1
    assert mgr.get_row("x.py::h")["churn"] == 7
    mgr.stop()


def test_manager_scoped_put_preserves_other_files(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    mgr = BlockCacheManager(repo, flush_interval_s=999)
    mgr.put_rows([
        {"path": "a.py::f", "churn": 1},
        {"path": "b.py::g", "churn": 2},
    ])
    mgr.put_rows(
        [{"path": "a.py::f", "churn": 99}],
        targeted_files={"a.py"},
    )
    assert mgr.get_row("a.py::f")["churn"] == 99
    assert mgr.get_row("b.py::g")["churn"] == 2
    mgr.stop()


def test_manager_flush_writes_to_disk(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    mgr = BlockCacheManager(repo, flush_interval_s=999)
    mgr.put_rows([{"path": "a.py::f", "churn": 5}])
    wrote = mgr.flush()
    assert wrote is True
    assert not mgr.modified
    loaded = load_block_results(repo)
    assert loaded is not None
    assert len(loaded) == 1
    assert loaded[0]["path"] == "a.py::f"
    mgr.stop()


def test_manager_flush_noop_when_clean(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    mgr = BlockCacheManager(repo, flush_interval_s=999)
    assert mgr.flush() is False
    mgr.stop()


def test_manager_loads_from_disk_on_init(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    save_block_results(repo, [{"path": "x.py::f", "churn": 42}])
    mgr = BlockCacheManager(repo, flush_interval_s=999)
    assert mgr.entry_count == 1
    assert mgr.get_row("x.py::f")["churn"] == 42
    assert not mgr.modified
    mgr.stop()


def test_manager_clear_removes_in_memory_and_disk(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    mgr = BlockCacheManager(repo, flush_interval_s=999)
    mgr.put_rows([{"path": "a.py::f", "churn": 1}])
    mgr.flush()
    mgr.clear()
    assert mgr.entry_count == 0
    assert not (cache_path_for(repo) / _CACHE_FILE).exists()
    mgr.stop()


def test_manager_get_previous_rows_index(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    mgr = BlockCacheManager(repo, flush_interval_s=999)
    mgr.put_rows([
        {"path": "a.py::f", "churn": 1},
        {"path": "b.py::g", "churn": 2},
    ])
    idx = mgr.get_previous_rows_index()
    assert isinstance(idx, dict)
    assert "a.py::f" in idx
    assert "b.py::g" in idx
    mgr.stop()


def test_manager_periodic_flush_writes_in_background(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    mgr = BlockCacheManager(repo, flush_interval_s=0.15)
    mgr.start_periodic_flush()
    mgr.put_rows([{"path": "a.py::f", "churn": 77}])
    deadline = time.monotonic() + 3.0
    loaded = None
    while time.monotonic() < deadline:
        time.sleep(0.1)
        loaded = load_block_results(repo)
        if loaded:
            break
    mgr.stop()
    assert loaded is not None, "periodic flush did not write within 3 s"
    assert len(loaded) == 1
    assert loaded[0]["churn"] == 77


def test_manager_concurrent_put_and_read(tmp_path: Path):
    """Multiple writers and a reader run concurrently without crashes."""
    repo = tmp_path / "repo"
    repo.mkdir()
    mgr = BlockCacheManager(repo, flush_interval_s=999)
    barrier = threading.Barrier(4)
    errors: list[Exception] = []

    def writer(wid: int) -> None:
        try:
            barrier.wait()
            for j in range(50):
                mgr.put_row({"path": f"w{wid}.py::f{j}", "churn": j})
        except Exception as exc:
            errors.append(exc)

    def reader() -> None:
        try:
            barrier.wait()
            for _ in range(100):
                mgr.entry_count
                mgr.get_all_rows()
        except Exception as exc:
            errors.append(exc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futs = [
            ex.submit(writer, 1),
            ex.submit(writer, 2),
            ex.submit(writer, 3),
            ex.submit(reader),
        ]
        for f in futs:
            f.result()

    assert not errors, f"concurrent errors: {errors}"
    assert mgr.entry_count == 150
    mgr.stop()


def test_manager_stop_is_idempotent(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    mgr = BlockCacheManager(repo, flush_interval_s=999)
    mgr.stop()
    mgr.stop()  # should not raise
