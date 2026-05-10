"""Tests for :mod:`hotspottriage.mcp_errors`."""

import json
import subprocess

import pytest

from hotspottriage.mcp_errors import mcp_classify_exception, mcp_tool_error


def test_mcp_tool_error_shape():
    raw = mcp_tool_error("X_CODE", "hello", details={"k": 1})
    data = json.loads(raw)
    assert data == {"error": {"code": "X_CODE", "message": "hello", "details": {"k": 1}}}


def test_mcp_classify_value_error_invalid_target():
    code, msg, det = mcp_classify_exception(
        ValueError("MCP tool requires a non-empty target")
    )
    assert code == "INVALID_TARGET"
    assert det == {}


def test_mcp_classify_called_process_error_git():
    err = subprocess.CalledProcessError(1, ["git", "status"], output="", stderr="nope")
    code, msg, det = mcp_classify_exception(err)
    assert code == "GIT_ERROR"
    assert det["returncode"] == 1
    assert det["cmd"] == ["git", "status"]
