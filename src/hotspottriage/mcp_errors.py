"""MCP tool error payloads and exception-to-code mapping for :mod:`hotspottriage.mcp_server`."""
from __future__ import annotations

import json
import subprocess
from typing import Any


def mcp_tool_error(
    code: str, message: str, *, details: dict[str, Any] | None = None
) -> str:
    """JSON body for MCP tool failures: ``{\"error\": {\"code\", \"message\", \"details\"}}``."""
    payload: dict[str, Any] = {
        "code": code,
        "message": message,
        "details": dict(details or {}),
    }
    return json.dumps({"error": payload}, indent=2)


def mcp_classify_exception(exc: BaseException) -> tuple[str, str, dict[str, Any]]:
    """Map an exception to ``(code, message, details)`` for :func:`mcp_tool_error`."""
    msg = str(exc)
    low = msg.lower()

    if isinstance(exc, NotADirectoryError):
        return "TARGET_NOT_FOUND", msg, {
            "path": str(getattr(exc, "filename", "") or ""),
        }
    if isinstance(exc, FileNotFoundError):
        return "TARGET_NOT_FOUND", msg, {
            "path": str(getattr(exc, "filename", "") or ""),
        }
    if isinstance(exc, PermissionError):
        return "CACHE_ERROR", msg, {}

    if isinstance(exc, subprocess.CalledProcessError):
        cp: subprocess.CalledProcessError = exc
        detail: dict[str, Any] = {
            "returncode": int(cp.returncode),
        }
        if cp.cmd is not None:
            detail["cmd"] = cp.cmd if isinstance(cp.cmd, str) else list(cp.cmd)
        stderr = (cp.stderr or "").strip() if isinstance(cp.stderr, str) else ""
        stdout = (cp.stdout or "").strip() if isinstance(cp.stdout, str) else ""
        if stderr:
            detail["stderr"] = stderr[:8192]
        if stdout:
            detail["stdout"] = stdout[:8192]
        return "GIT_ERROR", msg, detail

    if isinstance(exc, RuntimeError) and "not a git repository" in low:
        return "TARGET_NOT_FOUND", msg, {}

    if isinstance(exc, ValueError):
        if (
            "non-empty target" in low
            or "mcp tool requires a non-empty" in low
            or ("must be non-empty" in low and "path" in low)
        ):
            return "INVALID_TARGET", msg, {}
        if "exceeds maximum" in low or ("nul" in low and "path" in low):
            return "INVALID_TARGET", msg, {}
        if "local filesystem path is required" in low:
            return "INVALID_TARGET", msg, {"reason": "local_path_required"}
        if "local git repository" in low and "remote" in low:
            return "INVALID_TARGET", msg, {"reason": "revision_snapshot_requires_local_repo"}
        if "no cached snapshot" in low:
            return "SNAPSHOT_NOT_FOUND", msg, {}
        if "after_sha requires before_sha" in low:
            return "INVALID_ARGUMENT", msg, {}
        if "before_sha and after_sha require" in low and "remote" in low:
            return "INVALID_TARGET", msg, {"reason": "revision_snapshot_requires_local_repo"}
        if "invalid path:" in low:
            return "TARGET_NOT_FOUND", msg, {}
        cfg_markers = (
            "score_metrics",
            "limit must",
            "granularity",
            "smell_",
            "metric_normalization",
            "score_aggregation",
            "directories",
            "decay_half_life",
            "block_workers",
            "smell_weight",
            "proposed_models",
            "cannot read config",
            "invalid yaml",
        )
        if any(m in low for m in cfg_markers):
            return "CONFIG_VALIDATION", msg, {}
        if "ignore_directories" in low or "glob" in low or "pattern" in low:
            return "INVALID_FILTER", msg, {}
        return "INVALID_ARGUMENT", msg, {}

    if isinstance(exc, FileExistsError):
        return "CONFIG_VALIDATION", msg, {}

    if isinstance(exc, OSError):
        return "CACHE_ERROR", msg, {"errno": getattr(exc, "errno", None)}

    return "INTERNAL", msg, {"exception_type": type(exc).__name__}
