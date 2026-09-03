"""Per-directory dashboard singleton: detect an already-running local server.

Lock file: ``<project>/.hotspottriage/dashboard_server.json``.
Used so a second MCP/process for the same directory does not bind another
port or open another browser window.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from hotspottriage.path_utils import sanitize_log_value

logger = logging.getLogger(__name__)

LOCK_FILENAME = "dashboard_server.json"
_HEALTH_TIMEOUT_S = 1.5


def dashboard_lock_path(project_dir: Path) -> Path:
    """Return the lock file path under the project's ``.hotspottriage`` dir."""
    root = Path(project_dir).expanduser().resolve()
    return root / ".hotspottriage" / LOCK_FILENAME


def write_dashboard_lock(
    project_dir: Path,
    *,
    host: str,
    port: int,
    pid: int | None = None,
) -> Path:
    """Persist ownership metadata for the dashboard bound to *project_dir*."""
    root = Path(project_dir).expanduser().resolve()
    path = dashboard_lock_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "pid": int(os.getpid() if pid is None else pid),
        "host": str(host).strip() or "127.0.0.1",
        "port": int(port),
        "project_path": str(root),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def clear_dashboard_lock(project_dir: Path, *, pid: int | None = None) -> bool:
    """Remove the lock if missing owner check fails or *pid* matches (or is omitted).

    Returns True when the file was removed.
    """
    path = dashboard_lock_path(project_dir)
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        try:
            path.unlink()
            return True
        except OSError:
            return False
    if pid is not None:
        try:
            locked_pid = int(data.get("pid", -1))
        except (TypeError, ValueError):
            locked_pid = -1
        if locked_pid != int(pid):
            return False
    try:
        path.unlink()
        return True
    except OSError:
        return False


def _pid_seems_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we cannot signal it.
        return True
    except OSError:
        return False
    return True


def _fetch_health(host: str, port: int) -> dict[str, Any] | None:
    url = f"http://{host}:{int(port)}/api/health"
    try:
        with urllib.request.urlopen(url, timeout=_HEALTH_TIMEOUT_S) as resp:
            raw = resp.read()
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def find_running_dashboard_for_project(project_dir: Path) -> dict[str, Any] | None:
    """Return lock+health info if a dashboard for *project_dir* is already up.

    Shape: ``{host, port, pid, project_path, base_url}``. Returns ``None`` when
    no usable instance exists (missing/stale lock or health mismatch).
    """
    root = Path(project_dir).expanduser().resolve()
    path = dashboard_lock_path(root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.info(
            "Ignoring unreadable dashboard lock at %s",
            sanitize_log_value(str(path)),
        )
        return None
    if not isinstance(data, dict):
        return None
    try:
        host = str(data.get("host") or "127.0.0.1").strip() or "127.0.0.1"
        port = int(data["port"])
        pid = int(data.get("pid", -1))
        locked_project = str(data.get("project_path") or "").strip()
    except (KeyError, TypeError, ValueError):
        return None

    if locked_project:
        try:
            if Path(locked_project).expanduser().resolve() != root:
                return None
        except OSError:
            return None

    if not _pid_seems_alive(pid):
        logger.info(
            "Stale dashboard lock (dead pid %s) at %s — clearing",
            pid,
            sanitize_log_value(str(path)),
        )
        clear_dashboard_lock(root)
        return None

    health = _fetch_health(host, port)
    if health is None or health.get("status") != "alive":
        logger.info(
            "Stale dashboard lock (health failed) at %s — clearing",
            sanitize_log_value(str(path)),
        )
        clear_dashboard_lock(root)
        return None

    health_project = str(health.get("project_path") or "").strip()
    if health_project:
        try:
            if Path(health_project).expanduser().resolve() != root:
                return None
        except OSError:
            return None

    return {
        "host": host,
        "port": port,
        "pid": pid,
        "project_path": str(root),
        "base_url": f"http://{host}:{port}",
    }
