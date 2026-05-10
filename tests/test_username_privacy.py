"""Tests for GDPR-oriented username redaction in logs and structured redaction helpers."""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from hotspottriage.cache import load_block_results, save_block_results
from hotspottriage.username_privacy import (
    UsernameRedactingFormatter,
    redact_usernames_in_structure,
    redact_usernames_in_text,
    redaction_token_for_username,
    username_redaction_tokens,
)


@pytest.fixture(autouse=True)
def _clear_username_cache():
    username_redaction_tokens.cache_clear()
    yield
    username_redaction_tokens.cache_clear()


def test_redaction_token_for_username() -> None:
    assert redaction_token_for_username("alice") == "a****e"
    assert redaction_token_for_username("ab") == "a****b"
    assert redaction_token_for_username("x") == "x****"
    assert redaction_token_for_username("") == "****"


def test_redact_usernames_in_text_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USER", "alice")
    username_redaction_tokens.cache_clear()
    assert "alice" not in redact_usernames_in_text("/Users/alice/projects/foo")
    assert "a****e" in redact_usernames_in_text("/Users/alice/projects/foo")


def test_longest_token_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USER", "bob")
    monkeypatch.setenv("LOGNAME", "bobbuilder")
    username_redaction_tokens.cache_clear()
    out = redact_usernames_in_text("bobbuilder and bob")
    assert "bobbuilder" not in out
    assert "b****r" in out


def test_redact_usernames_in_structure_nested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("USER", "carol")
    username_redaction_tokens.cache_clear()
    raw = {
        "path": "src/x.py::f",
        "note": "/home/carol/ws",
        "nested": [{"p": "/Users/carol/x"}],
    }
    red = redact_usernames_in_structure(raw)
    assert red["path"] == "src/x.py::f"
    assert "carol" not in red["note"]
    assert "c****l" in red["note"]
    assert "carol" not in red["nested"][0]["p"]


def test_save_block_results_preserves_string_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("USER", "alice")
    username_redaction_tokens.cache_clear()
    repo = tmp_path / "repo"
    repo.mkdir()
    note = "/home/alice/project"
    rows = [{"path": "f::g", "note": note}]
    save_block_results(repo, rows)
    loaded = load_block_results(repo)
    assert loaded is not None
    assert loaded[0]["path"] == "f::g"
    assert loaded[0]["note"] == note


def test_username_redacting_formatter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USER", "dave")
    username_redaction_tokens.cache_clear()
    fmt = UsernameRedactingFormatter("%(message)s")
    record = logging.LogRecord(
        name="t",
        level=logging.INFO,
        pathname="p",
        lineno=1,
        msg="/home/dave/r",
        args=(),
        exc_info=None,
    )
    line = fmt.format(record)
    assert "dave" not in line
    assert "d****e" in line
