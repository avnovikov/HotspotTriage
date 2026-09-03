"""Tests for per-directory dashboard instance lock / reuse."""
from __future__ import annotations

import json
import os
from pathlib import Path

from hotspottriage.dashboard import instance_lock as lock


def test_write_and_clear_dashboard_lock(tmp_path: Path):
    path = lock.write_dashboard_lock(tmp_path, host="127.0.0.1", port=9123)
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["port"] == 9123
    assert data["pid"] == os.getpid()
    assert Path(data["project_path"]).resolve() == tmp_path.resolve()
    assert lock.clear_dashboard_lock(tmp_path, pid=os.getpid()) is True
    assert not path.is_file()


def test_find_running_clears_stale_dead_pid(tmp_path: Path, monkeypatch):
    lock.write_dashboard_lock(tmp_path, host="127.0.0.1", port=65530, pid=999999)
    monkeypatch.setattr(lock, "_pid_seems_alive", lambda _pid: False)
    assert lock.find_running_dashboard_for_project(tmp_path) is None
    assert not lock.dashboard_lock_path(tmp_path).is_file()


def test_find_running_returns_when_health_ok(tmp_path: Path, monkeypatch):
    lock.write_dashboard_lock(tmp_path, host="127.0.0.1", port=9123, pid=os.getpid())
    monkeypatch.setattr(lock, "_pid_seems_alive", lambda _pid: True)

    def _health(host: str, port: int):
        assert host == "127.0.0.1"
        assert port == 9123
        return {
            "status": "alive",
            "project_path": str(tmp_path.resolve()),
            "pid": os.getpid(),
        }

    monkeypatch.setattr(lock, "_fetch_health", _health)
    found = lock.find_running_dashboard_for_project(tmp_path)
    assert found is not None
    assert found["base_url"] == "http://127.0.0.1:9123"
    assert found["project_path"] == str(tmp_path.resolve())


def test_find_running_rejects_health_project_mismatch(tmp_path: Path, monkeypatch):
    lock.write_dashboard_lock(tmp_path, host="127.0.0.1", port=9123, pid=os.getpid())
    monkeypatch.setattr(lock, "_pid_seems_alive", lambda _pid: True)
    monkeypatch.setattr(
        lock,
        "_fetch_health",
        lambda *_a, **_k: {
            "status": "alive",
            "project_path": str(tmp_path / "other"),
        },
    )
    assert lock.find_running_dashboard_for_project(tmp_path) is None
