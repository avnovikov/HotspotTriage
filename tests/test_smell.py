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


def _thresholds(
    *,
    max_comment_ratio: float = 0.5,
    max_comment_block_lines: int = 15,
    data_class_min_attributes: int = 8,
    middle_man_max_avg_method_sloc: float = 2.0,
    speculative_generality_min_hits: int = 1,
) -> dict:
    return {
        "max_statements": 50,
        "max_attributes": 10,
        "max_public_methods": 20,
        "max_args": 5,
        "max_branches": 12,
        "min_public_methods": 2,
        "max_comment_ratio": max_comment_ratio,
        "max_comment_block_lines": max_comment_block_lines,
        "data_class_min_attributes": data_class_min_attributes,
        "middle_man_max_avg_method_sloc": middle_man_max_avg_method_sloc,
        "speculative_generality_min_hits": speculative_generality_min_hits,
    }


def test_compute_smells_adds_excessive_comments(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    target = tmp_path / "comments.py"
    target.write_text(
        "# c1\n"
        "# c2\n"
        "# c3\n"
        "x = 1\n"
        "# c4\n"
    )

    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(returncode=0, stdout="[]", stderr="")

    monkeypatch.setattr(smell.subprocess, "run", fake_run)
    monkeypatch.setattr(smell, "_default_thresholds", lambda: _thresholds(max_comment_ratio=0.1))

    out = smell.compute_smells(target)
    finding = next(f for f in out if f["smell"] == "excessive_comments")
    assert finding["file"] == str(target)
    assert finding["line"] == 1
    assert "exceeds threshold" in finding["message"]


def test_compute_smells_adds_large_comment_block(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    target = tmp_path / "block.py"
    target.write_text(
        "# a\n"
        "# b\n"
        "# c\n"
        "# d\n"
        "x = 1\n"
    )

    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(returncode=0, stdout="[]", stderr="")

    monkeypatch.setattr(smell.subprocess, "run", fake_run)
    monkeypatch.setattr(
        smell, "_default_thresholds", lambda: _thresholds(max_comment_ratio=99.0, max_comment_block_lines=2)
    )

    out = smell.compute_smells(target)
    finding = next(f for f in out if f["smell"] == "large_comment_block")
    assert finding["file"] == str(target)
    assert finding["line"] == 1
    assert "length 4" in finding["message"]


def test_compute_smells_adds_data_class_with_approximate_confidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    target = tmp_path / "dc.py"
    target.write_text(
        "class DataThing:\n"
        "    def __init__(self):\n"
        "        self.a = self.b = self.c = self.d = self.e = self.f = self.g = self.h = 1\n"
        "    def ping(self):\n"
        "        return 1\n"
    )
    payload = [
        {"path": str(target), "line": 1, "obj": "DataThing", "message-id": "R0903", "message": "Too few public methods (1/2)"},
        {"path": str(target), "line": 1, "obj": "DataThing", "message-id": "R0902", "message": "Too many instance attributes (8/7)"},
    ]

    monkeypatch.setattr(
        smell.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=16, stdout=json.dumps(payload), stderr=""),
    )
    monkeypatch.setattr(smell, "_default_thresholds", lambda: _thresholds(data_class_min_attributes=7))
    out = smell.compute_smells(target)
    data_class = next(f for f in out if f["smell"] == "data_class")
    assert data_class["confidence"] == "approximate"


def test_compute_smells_middle_man_positive_and_negative(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    positive = tmp_path / "mm_yes.py"
    positive.write_text(
        "class Broker:\n"
        "    def a(self):\n"
        "        return ext.a()\n"
        "    def b(self):\n"
        "        return ext.b()\n"
    )
    negative = tmp_path / "mm_no.py"
    negative.write_text(
        "class Broker:\n"
        "    def a(self):\n"
        "        x = 0\n"
        "        for i in range(5):\n"
        "            x += i\n"
        "        return x\n"
    )

    pos_payload = [{"path": str(positive), "line": 1, "obj": "Broker", "message-id": "R0903", "message": "Too few public methods (2/3)"}]
    neg_payload = [{"path": str(negative), "line": 1, "obj": "Broker", "message-id": "R0903", "message": "Too few public methods (1/2)"}]

    monkeypatch.setattr(
        smell.subprocess,
        "run",
        lambda args, **_kwargs: SimpleNamespace(
            returncode=16,
            stdout=json.dumps(pos_payload if str(positive) in args else neg_payload),
            stderr="",
        ),
    )
    monkeypatch.setattr(smell, "_default_thresholds", lambda: _thresholds(middle_man_max_avg_method_sloc=2.0))

    pos_out = smell.compute_smells(positive)
    neg_out = smell.compute_smells(negative)
    assert any(f["smell"] == "middle_man" and f["confidence"] == "approximate" for f in pos_out)
    assert not any(f["smell"] == "middle_man" for f in neg_out)


def test_compute_smells_speculative_generality_positive_and_negative(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    target = tmp_path / "sg.py"
    target.write_text("x = 1\n")
    positive_payload = [
        {"path": str(target), "line": 1, "obj": "", "message-id": "W0611", "message": "Unused import os"},
        {"path": str(target), "line": 2, "obj": "", "message-id": "W0612", "message": "Unused variable y"},
    ]
    negative_payload = [
        {"path": str(target), "line": 1, "obj": "", "message-id": "W0611", "message": "Unused import os"},
    ]

    monkeypatch.setattr(
        smell.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=4, stdout=json.dumps(positive_payload), stderr=""),
    )
    monkeypatch.setattr(smell, "_default_thresholds", lambda: _thresholds(speculative_generality_min_hits=1))
    out = smell.compute_smells(target)
    assert any(f["smell"] == "speculative_generality" and f["confidence"] == "approximate" for f in out)

    monkeypatch.setattr(
        smell.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=4, stdout=json.dumps(negative_payload), stderr=""),
    )
    out_negative = smell.compute_smells(target)
    assert not any(f["smell"] == "speculative_generality" for f in out_negative)


def test_finding_applies_to_block_line_range():
    from hotspottriage.blocks import Block

    finding = {"line": 15, "smell": "long_method"}
    assert smell.finding_applies_to_block(finding, Block("foo", 10, 20))
    assert not smell.finding_applies_to_block(finding, Block("foo", 1, 5))


def test_finding_applies_to_block_class_scope_matches_methods_not_file_line():
    """Class-line pylint rows must still attach to each method block under that class."""
    from hotspottriage.blocks import Block

    finding = {
        "line": 3,
        "smell": "data_class",
        "scope": {"kind": "class", "symbol": "Foo"},
    }
    assert smell.finding_applies_to_block(finding, Block("Foo.bar", 10, 25))
    assert smell.finding_applies_to_block(finding, Block("Foo.baz", 30, 40))
    assert not smell.finding_applies_to_block(finding, Block("top", 1, 5))
    assert smell.finding_applies_to_block(finding, Block("Foo.Inner.m", 50, 60))


def test_finding_applies_to_block_class_scope_does_not_match_wrong_prefix():
    from hotspottriage.blocks import Block

    finding = {"line": 1, "smell": "x", "scope": {"kind": "class", "symbol": "Foo"}}
    assert not smell.finding_applies_to_block(finding, Block("FooBar.spam", 2, 9))


def test_summarize_smells_counts_by_smell_id():
    findings = [
        {"smell": "long_method", "message": "a"},
        {"smell": "long_method", "message": "b"},
        {"smell": "long_parameter_list", "message": "c"},
    ]
    s = smell.summarize_smells(findings)
    assert s == {"long_method": 2, "long_parameter_list": 1}
