"""Strict handling for user-supplied filesystem paths (dashboard, MCP, CLI helpers)."""
from __future__ import annotations

from pathlib import Path

from hotspottriage.discovery import is_git_url

# Generous cap for paths and filter strings at HTTP/MCP boundaries.
MAX_TARGET_PATH_STR_LEN = 4096


def assert_bounded_path_string(s: str, *, label: str = "path") -> str:
    """Reject empty (after strip), oversize, or NUL-containing path strings."""
    t = str(s).strip()
    if not t:
        raise ValueError(f"{label} must be non-empty")
    if len(t) > MAX_TARGET_PATH_STR_LEN:
        raise ValueError(f"{label} exceeds maximum allowed length ({MAX_TARGET_PATH_STR_LEN})")
    if "\x00" in t:
        raise ValueError(f"{label} must not contain NUL bytes")
    return t


def resolve_local_repo_path(raw: str) -> Path:
    """Resolve a **local** repository path to an absolute :class:`Path`.

    Remote git URLs (``http(s)://…``, ``git@…``, etc.) are rejected; callers that
    accept URLs must branch on :func:`hotspottriage.discovery.is_git_url` first.
    """
    t = assert_bounded_path_string(raw, label="target path")
    if is_git_url(t):
        raise ValueError("A local filesystem path is required; remote git URLs are not supported here.")
    p = Path(t).expanduser()
    try:
        return p.resolve()
    except OSError as e:
        raise ValueError(f"invalid path: {e}") from e


def sanitize_log_value(value: str, *, max_len: int = 512) -> str:
    """Make a value safe for structured log formatters (mitigate log injection)."""
    s = str(value).replace("\r", "\\r").replace("\n", "\\n")
    if len(s) > max_len:
        return s[: max_len - 1] + "…"
    return s


def normalize_user_target_string(raw: str) -> str:
    """Normalize a user ``target`` string: locals to absolute paths; git URLs unchanged.

    Used by the dashboard when persisting ``last_target`` and forwarding to the
    analysis pipeline (which accepts remote URLs).
    """
    t = str(raw).strip()
    if not t:
        return ""
    if is_git_url(t):
        assert_bounded_path_string(t, label="target")
        return t
    return str(resolve_local_repo_path(t))
