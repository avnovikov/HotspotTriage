"""MCP tool error payloads and exception-to-code mapping (used by :mod:`hotspottriage.mcp_server`)."""
from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
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


def _called_process_error_details(cp: subprocess.CalledProcessError) -> dict[str, Any]:
    detail: dict[str, Any] = {"returncode": int(cp.returncode)}
    if cp.cmd is not None:
        detail["cmd"] = cp.cmd if isinstance(cp.cmd, str) else list(cp.cmd)
    stderr = (cp.stderr or "").strip() if isinstance(cp.stderr, str) else ""
    stdout = (cp.stdout or "").strip() if isinstance(cp.stdout, str) else ""
    if stderr:
        detail["stderr"] = stderr[:8192]
    if stdout:
        detail["stdout"] = stdout[:8192]
    return detail


def _ve_invalid_target_empty_or_path(low: str) -> bool:
    return (
        "non-empty target" in low
        or "mcp tool requires a non-empty" in low
        or ("must be non-empty" in low and "path" in low)
        or "exceeds maximum" in low
        or ("nul" in low and "path" in low)
    )


def _ve_invalid_target_local_required(low: str) -> bool:
    return "local filesystem path is required" in low


def _ve_invalid_target_revision_remote(low: str) -> bool:
    return "local git repository" in low and "remote" in low


def _ve_snapshot_not_found(low: str) -> bool:
    return "no cached snapshot" in low


def _ve_invalid_argument_after_sha(low: str) -> bool:
    return "after_sha requires before_sha" in low


def _ve_invalid_target_sha_remote(low: str) -> bool:
    return "before_sha and after_sha require" in low and "remote" in low


def _ve_target_not_found_path(low: str) -> bool:
    return "invalid path:" in low


def _ve_config_validation(low: str) -> bool:
    markers = (
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
    return any(m in low for m in markers)


def _ve_invalid_filter(low: str) -> bool:
    return "ignore_directories" in low or "glob" in low or "pattern" in low


# (predicate, code, details) — first match wins.
_VALUE_ERROR_RULES: tuple[
    tuple[Callable[[str], bool], str, dict[str, Any]], ...
] = (
    (_ve_invalid_target_empty_or_path, "INVALID_TARGET", {}),
    (_ve_invalid_target_local_required, "INVALID_TARGET", {"reason": "local_path_required"}),
    (_ve_invalid_target_revision_remote, "INVALID_TARGET", {"reason": "revision_snapshot_requires_local_repo"}),
    (_ve_snapshot_not_found, "SNAPSHOT_NOT_FOUND", {}),
    (_ve_invalid_argument_after_sha, "INVALID_ARGUMENT", {}),
    (_ve_invalid_target_sha_remote, "INVALID_TARGET", {"reason": "revision_snapshot_requires_local_repo"}),
    (_ve_target_not_found_path, "TARGET_NOT_FOUND", {}),
    # Before config markers: ``ignore_directories`` messages contain the substring ``directories``.
    (_ve_invalid_filter, "INVALID_FILTER", {}),
    (_ve_config_validation, "CONFIG_VALIDATION", {}),
)


def _classify_value_error(msg: str, low: str) -> tuple[str, str, dict[str, Any]]:
    """Map :class:`ValueError` text to MCP error tuple."""
    for pred, code, details in _VALUE_ERROR_RULES:
        if pred(low):
            return code, msg, dict(details)
    return "INVALID_ARGUMENT", msg, {}


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
        return "GIT_ERROR", msg, _called_process_error_details(exc)

    if isinstance(exc, RuntimeError) and "not a git repository" in low:
        return "TARGET_NOT_FOUND", msg, {}

    if isinstance(exc, ValueError):
        return _classify_value_error(msg, low)

    if isinstance(exc, FileExistsError):
        return "CONFIG_VALIDATION", msg, {}

    if isinstance(exc, OSError):
        return "CACHE_ERROR", msg, {"errno": getattr(exc, "errno", None)}

    return "INTERNAL", msg, {"exception_type": type(exc).__name__}
