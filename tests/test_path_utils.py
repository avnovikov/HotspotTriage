"""Tests for hotspottriage.path_utils."""
from __future__ import annotations

import pytest

from hotspottriage.path_utils import (
    MAX_TARGET_PATH_STR_LEN,
    normalize_user_target_string,
    resolve_local_repo_path,
    sanitize_log_value,
)


def test_sanitize_log_value_strips_newlines():
    s = sanitize_log_value("a\nfake\rentry")
    assert "\n" not in s
    assert "\r" not in s


def test_resolve_local_repo_path_rejects_git_url():
    with pytest.raises(ValueError, match="local filesystem path"):
        resolve_local_repo_path("https://example.com/repo.git")


def test_normalize_user_target_string_accepts_git_url():
    assert normalize_user_target_string("https://example.com/repo.git") == "https://example.com/repo.git"


def test_resolve_local_repo_path_rejects_oversized():
    with pytest.raises(ValueError, match="maximum"):
        resolve_local_repo_path("x" * (MAX_TARGET_PATH_STR_LEN + 1))
