"""Complexity strategies, all backed by radon's Python AST analyzers.

Each strategy returns an int so it can be multiplied with churn to produce a
score. Maintainability is inverted (100 - MI) so "higher = worse" matches the
other metrics.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

from radon.complexity import cc_visit
from radon.metrics import h_visit, mi_visit
from radon.raw import analyze

Strategy = str
STRATEGIES: tuple[Strategy, ...] = ("sloc", "cyclomatic", "halstead", "maintainability")


def _sloc(src: str) -> int:
    return analyze(src).sloc


def _cyclomatic(src: str) -> int:
    # Sum complexity across all functions/methods/classes in the module.
    # Matches what `radon cc <file>` reports as the per-file total.
    return sum(block.complexity for block in cc_visit(src))


def _halstead(src: str) -> int:
    return int(round(h_visit(src).total.volume))


def _maintainability(src: str) -> int:
    # mi_visit returns 0..100 where 100 = most maintainable.
    # Invert so higher score = worse, consistent with the other metrics.
    mi = mi_visit(src, True)
    return max(0, int(round(100 - mi)))


_DISPATCH: dict[Strategy, Callable[[str], int]] = {
    "sloc": _sloc,
    "cyclomatic": _cyclomatic,
    "halstead": _halstead,
    "maintainability": _maintainability,
}


def compute(path: Path, strategy: Strategy) -> int:
    """Compute complexity for a single Python file. Returns 0 on parse errors."""
    if strategy not in _DISPATCH:
        raise ValueError(f"unknown strategy: {strategy!r} (valid: {STRATEGIES})")
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"warning: cannot read {path}: {e}", file=sys.stderr)
        return 0
    try:
        return _DISPATCH[strategy](src)
    except (SyntaxError, ValueError) as e:
        # radon raises SyntaxError on unparseable Python; ValueError on empty halstead etc.
        print(f"warning: cannot analyze {path}: {e}", file=sys.stderr)
        return 0
