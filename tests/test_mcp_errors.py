"""Tests for :mod:`hotspottriage.mcp.errors`."""

import json
import subprocess

import pytest

from hotspottriage.mcp.errors import mcp_classify_exception, mcp_tool_error


@pytest.mark.parametrize(
    ("message", "expected_code", "expected_details"),
    [
        (
            "MCP tool requires a non-empty target (local git repo path or remote URL), "
            "or start the server with --default-target PATH_OR_URL",
            "INVALID_TARGET",
            {},
        ),
        (
            "A local filesystem path is required; remote git URLs are not supported here.",
            "INVALID_TARGET",
            {"reason": "local_path_required"},
        ),
        (
            "before_sha and after_sha require a local git repository path, "
            "not a remote URL",
            "INVALID_TARGET",
            {"reason": "revision_snapshot_requires_local_repo"},
        ),
        ("after_sha requires before_sha", "INVALID_ARGUMENT", {}),
        (
            "no cached snapshot for abc123def (from rev 'HEAD~9'); "
            "run MCP analyze on a checkout at that commit first and use the returned "
            "`head_sha` so HotspotTriage can record metrics.",
            "SNAPSHOT_NOT_FOUND",
            {},
        ),
        ("invalid path: [Errno 2] No such file or directory: '/nope/repo'", "TARGET_NOT_FOUND", {}),
        ("score_metrics must be a non-empty list", "CONFIG_VALIDATION", {}),
        ("ignore_directories entry must be non-empty", "INVALID_FILTER", {}),
        ("unexpected free-form validation failure", "INVALID_ARGUMENT", {}),
        # Prefix-only target message still matches ``_ve_invalid_target_empty_or_path``.
        ("MCP tool requires a non-empty target", "INVALID_TARGET", {}),
    ],
)
def test_mcp_classify_value_error_production_shapes(
    message: str, expected_code: str, expected_details: dict
) -> None:
    """Regression: map ``ValueError`` text from MCP/analyze/path helpers to stable codes."""
    code, msg, det = mcp_classify_exception(ValueError(message))
    assert code == expected_code
    assert msg == message
    assert det == expected_details


def test_mcp_tool_error_shape():
    raw = mcp_tool_error("X_CODE", "hello", details={"k": 1})
    data = json.loads(raw)
    assert data == {"error": {"code": "X_CODE", "message": "hello", "details": {"k": 1}}}


def test_mcp_classify_called_process_error_git():
    err = subprocess.CalledProcessError(1, ["git", "status"], output="", stderr="nope")
    code, msg, det = mcp_classify_exception(err)
    assert code == "GIT_ERROR"
    assert det["returncode"] == 1
    assert det["cmd"] == ["git", "status"]


def test_mcp_classify_called_process_error_string_cmd_and_truncation() -> None:
    long_err = "e" * 9000
    err = subprocess.CalledProcessError(
        2,
        "git rev-parse HEAD",
        output="",
        stderr=long_err,
    )
    code, _msg, det = mcp_classify_exception(err)
    assert code == "GIT_ERROR"
    assert det["cmd"] == "git rev-parse HEAD"
    assert len(det["stderr"]) == 8192


def test_mcp_classify_not_a_directory_and_file_not_found() -> None:
    code, _m, d = mcp_classify_exception(NotADirectoryError(20, "Not a directory", "/tmp/x"))
    assert code == "TARGET_NOT_FOUND"
    assert d["path"] == "/tmp/x"

    code2, _m2, d2 = mcp_classify_exception(FileNotFoundError(2, "No such file", "/missing"))
    assert code2 == "TARGET_NOT_FOUND"
    assert d2["path"] == "/missing"


def test_mcp_classify_runtime_error_git_vs_other() -> None:
    code, _m, d = mcp_classify_exception(RuntimeError("fatal: not a git repository"))
    assert code == "TARGET_NOT_FOUND"
    assert d == {}

    code2, _m2, d2 = mcp_classify_exception(RuntimeError("something else"))
    assert code2 == "INTERNAL"
    assert d2["exception_type"] == "RuntimeError"


def test_mcp_classify_file_exists_and_oserror_and_generic() -> None:
    code, _m, d = mcp_classify_exception(FileExistsError(17, "exists", "/cfg"))
    assert code == "CONFIG_VALIDATION"
    assert d == {}

    code2, _m2, d2 = mcp_classify_exception(OSError(5, "I/O error"))
    assert code2 == "CACHE_ERROR"
    assert d2.get("errno") == 5

    code3, _m3, d3 = mcp_classify_exception(KeyError("missing"))
    assert code3 == "INTERNAL"
    assert d3["exception_type"] == "KeyError"


def test_mcp_classify_permission_error_cache() -> None:
    code, _m, d = mcp_classify_exception(PermissionError(13, "denied", "/cache"))
    assert code == "CACHE_ERROR"
    assert d == {}
