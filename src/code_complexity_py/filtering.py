"""Glob filtering with the original tool's AND semantics.

Each pattern is treated independently. A leading `!` negates that single
pattern. A file is kept iff it satisfies *all* patterns (AND), matching the
behaviour of the original `code-complexity` tool which calls
`micromatch.isMatch(file, pattern)` for every pattern and ANDs the results.
"""
from __future__ import annotations

from typing import Callable, Iterable

import pathspec


def _compile_one(pattern: str) -> tuple[pathspec.PathSpec, bool]:
    negated = pattern.startswith("!")
    if negated:
        pattern = pattern[1:]
    spec = pathspec.PathSpec.from_lines("gitignore", [pattern])
    return spec, negated


def make_filter(patterns: Iterable[str]) -> Callable[[str], bool]:
    """Return a predicate over POSIX-style relative paths."""
    compiled = [_compile_one(p.strip()) for p in patterns if p and p.strip()]
    if not compiled:
        return lambda _: True

    def keep(path: str) -> bool:
        return all((spec.match_file(path) ^ negated) for spec, negated in compiled)

    return keep
