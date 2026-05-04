"""Complexity metrics for a Python file, all computed via radon's AST analyzers.

`compute_all` returns all four metrics in one go from a single read of the file:

  - sloc            : source lines (radon.raw, excludes blanks/comments)
  - cyclomatic      : sum of McCabe complexity across all functions/methods/classes
  - halstead        : Halstead volume, rounded to int
  - maintainability : 100 - radon's MI score, so higher = worse (consistent with the others)

Files that fail to parse return zeros for the parsed metrics and emit a stderr warning.
"""
from __future__ import annotations

import sys
from pathlib import Path

from radon.complexity import cc_visit
from radon.metrics import h_visit, mi_visit
from radon.raw import analyze

METRICS: tuple[str, ...] = ("sloc", "cyclomatic", "halstead", "maintainability")


def _sloc(src: str) -> int:
    return analyze(src).sloc


def _cyclomatic(src: str) -> int:
    return sum(block.complexity for block in cc_visit(src))


def _halstead(src: str) -> int:
    return int(round(h_visit(src).total.volume))


def _maintainability(src: str) -> int:
    return max(0, int(round(100 - mi_visit(src, True))))


def compute_all(path: Path) -> dict[str, int]:
    """Compute every metric for a single file. Returns zeros on parse errors."""
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"warning: cannot read {path}: {e}", file=sys.stderr)
        return {m: 0 for m in METRICS}

    out: dict[str, int] = {}
    for name, fn in (
        ("sloc", _sloc),
        ("cyclomatic", _cyclomatic),
        ("halstead", _halstead),
        ("maintainability", _maintainability),
    ):
        try:
            out[name] = fn(src)
        except (SyntaxError, ValueError) as e:
            print(f"warning: cannot analyze {path} ({name}): {e}", file=sys.stderr)
            out[name] = 0
    return out
