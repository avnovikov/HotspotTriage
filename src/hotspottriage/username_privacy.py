"""Detect OS-level username tokens and redact them for logs and UI-facing strings.

Redaction uses ``first + "****" + last`` for multi-character usernames, and
``name + "****"`` for a single character. On-disk block cache (``blocks.pkl``)
stores row dicts verbatim; redaction applies to logs, ``sanitize_log_value``, and
dashboard ``*_display`` fields—not to pickle cache payload writes.
"""
from __future__ import annotations

import getpass
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def username_redaction_tokens() -> tuple[str, ...]:
    """Return unique username strings to redact, longest first (substring safety)."""
    candidates: list[str] = []
    for key in ("USER", "LOGNAME", "USERNAME"):
        raw = os.environ.get(key)
        if raw and str(raw).strip():
            candidates.append(str(raw).strip())
    try:
        gu = getpass.getuser()
        if gu and str(gu).strip():
            candidates.append(str(gu).strip())
    except (OSError, RuntimeError) as e:
        logger.debug("getpass.getuser() unavailable for redaction hints: %s", e)
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE")
    if home:
        try:
            leaf = Path(home).name
            if leaf and leaf not in {".", ".."}:
                candidates.append(leaf)
        except OSError:
            pass

    seen: set[str] = set()
    ordered: list[str] = []
    for c in candidates:
        if not c or c in seen:
            continue
        seen.add(c)
        ordered.append(c)
    ordered.sort(key=len, reverse=True)
    return tuple(ordered)


def redaction_token_for_username(username: str) -> str:
    """Return the replacement token for *username*."""
    u = str(username)
    if len(u) <= 1:
        return f"{u}****" if u else "****"
    return f"{u[0]}****{u[-1]}"


def redact_usernames_in_text(text: str) -> str:
    """Replace configured username tokens in *text* (substring match, longest token first)."""
    if not text:
        return text
    s = str(text)
    for u in username_redaction_tokens():
        if not u:
            continue
        s = s.replace(u, redaction_token_for_username(u))
    return s


def redact_usernames_in_structure(obj: Any) -> Any:
    """Recursively redact string leaves in JSON-like trees (dict/list/tuple/set)."""
    if isinstance(obj, str):
        return redact_usernames_in_text(obj)
    if isinstance(obj, dict):
        return {k: redact_usernames_in_structure(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_usernames_in_structure(v) for v in obj]
    if isinstance(obj, tuple):
        return tuple(redact_usernames_in_structure(v) for v in obj)
    if isinstance(obj, (set, frozenset)):
        ctor = type(obj)
        return ctor(redact_usernames_in_structure(v) for v in obj)
    return obj


class UsernameRedactingFormatter(logging.Formatter):
    """``logging.Formatter`` that masks the local OS username in the final line."""

    def format(self, record: logging.LogRecord) -> str:
        return redact_usernames_in_text(super().format(record))
