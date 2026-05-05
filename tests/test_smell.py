from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from hotspottriage import smell


def test_compute_smells_maps_enabled_messages(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    target = tmp_path / "example.py"
    target.write_text("def f(a, b, c, d, e, f):\n    return a\n")
    payload = [
        {
            "type": "refactor",
            "module": "example",
            "obj": "f",
            "line": 1,
            "column": 0,
            "path": str(target),
            "symbol": "too-many-arguments",
            "message": "Too many arguments (6/5)",
            "message-id": "R0913",
        },
        {
            "type": "warning",
            "module": "example",
            "obj": "",
            "line": 2,
            "column": 0,
            "path": str(target),
            "symbol": "unused-variable",
            "message": "Unused variable 'x'",
            "message-id": "W0612",
        },
    ]

    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(returncode=16, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(smell.subprocess, "run", fake_run)
    out = smell.compute_smells(target)
    assert out == [
        {
            "file": str(target),
            "line": 1,
            "smell": "long_parameter_list",
            "message": "Too many arguments (6/5)",
        },
        {
            "file": str(target),
            "line": 2,
            "smell": "dead_code",
            "message": "Unused variable 'x'",
        },
    ]


def test_compute_smells_returns_empty_on_no_output(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    target = tmp_path / "example.py"
    target.write_text("def f():\n    return 1\n")

    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(smell.subprocess, "run", fake_run)
    assert smell.compute_smells(target) == []


def test_compute_smells_raises_when_pylint_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    target = tmp_path / "example.py"
    target.write_text("def f():\n    return 1\n")

    def fake_run(*_args, **_kwargs):
        raise FileNotFoundError("pylint")

    monkeypatch.setattr(smell.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="pylint executable not found"):
        smell.compute_smells(target)


def test_build_command_contains_threshold_flags():
    cmd = smell._build_pylint_command(
        Path("x.py"),
        {
            "max_statements": 60,
            "max_attributes": 12,
            "max_public_methods": 25,
            "max_args": 7,
            "max_branches": 15,
            "min_public_methods": 1,
        },
    )
    assert "--max-statements=60" in cmd
    assert "--max-attributes=12" in cmd
    assert "--max-public-methods=25" in cmd
    assert "--max-args=7" in cmd
    assert "--max-branches=15" in cmd
    assert "--min-public-methods=1" in cmd
