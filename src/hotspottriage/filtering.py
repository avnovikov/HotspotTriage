"""Glob filtering with the original tool's AND semantics.

Each pattern is treated independently. A leading `!` negates that single
pattern. A file is kept iff it satisfies *all* patterns (AND), matching the
behaviour of the original `code-complexity` tool which calls
`micromatch.isMatch(file, pattern)` for every pattern and ANDs the results.

Directory ignores (`ignore_directories`) drop any tracked path whose
relative path equals a prefix or starts with ``prefix + '/'``.

Gitignore-style rules (`.gitignore`, nested ``**/.gitignore``, and
``.git/info/exclude``) are applied to **tracked** paths the same way git
would for an untracked file: last matching pattern wins, including ``!``
negation. This excludes e.g. vendored trees that remain tracked but are
listed in ``.gitignore``.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable, Iterator

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


# --- Directory prefix ignores ---------------------------------------------


def normalize_directory_prefix(raw: str) -> str:
    """Normalise a user-supplied directory prefix to a POSIX path with no
    leading/trailing slashes, no `.` / `..` segments, and no backslashes.

    Raises ValueError with an actionable message on unsafe or empty input.
    """
    s = raw.strip().replace("\\", "/")
    if not s:
        raise ValueError("ignore_directories entry must be non-empty")
    while s.startswith("./"):
        s = s[2:]
    s = s.strip("/")
    if not s:
        raise ValueError("ignore_directories entry must not resolve to empty")
    parts = PurePosixPath(s).parts
    if ".." in parts:
        raise ValueError(
            f"ignore_directories entry must not contain '..'; got {raw!r}"
        )
    return str(PurePosixPath(*parts))


def is_under_directory_prefix(rel_posix: str, prefix: str) -> bool:
    """True if ``rel_posix`` is exactly ``prefix`` or lives under it."""
    if rel_posix == prefix:
        return True
    return rel_posix.startswith(prefix + "/")


def is_ignored_by_directory_prefixes(rel_posix: str, prefixes: Iterable[str]) -> bool:
    """True when ``rel_posix`` falls under any normalised prefix."""
    for p in prefixes:
        if is_under_directory_prefix(rel_posix, p):
            return True
    return False


# --- Gitignore rules on tracked paths -------------------------------------


def _rel_suffix_under_anchor(rel_posix: str, anchor: str) -> str | None:
    """Return the part of ``rel_posix`` relative to ``anchor``, or None if the
    path does not live under ``anchor`` (so that anchor's .gitignore does not
    apply). ``anchor`` is a normalised POSIX path without trailing slash, or
    the empty string for the repo root."""
    if anchor == "":
        return rel_posix
    if rel_posix == anchor:
        return ""
    if rel_posix.startswith(anchor + "/"):
        return rel_posix[len(anchor) + 1 :]
    return None


def _dir_ancestors_posix(dir_posix: str) -> list[str]:
    """Return ['', 'a', 'a/b', ...] for dir_posix == 'a/b' (root '' first)."""
    if not dir_posix:
        return [""]
    parts = dir_posix.split("/")
    out: list[str] = [""]
    for i in range(len(parts)):
        out.append("/".join(parts[: i + 1]))
    return out


def _iter_gitignore_rule_lines(repo: Path, rel_file_posix: str) -> Iterator[tuple[str, str]]:
    """Yield ``(anchor, raw_line)`` for every rule line that applies to
    ``rel_file_posix``, in evaluation order (later lines override earlier ones,
    and later files override earlier files for matching lines)."""
    parent = str(PurePosixPath(rel_file_posix).parent)
    if parent == ".":
        parent = ""
    anchors = _dir_ancestors_posix(parent)

    seen_paths: set[Path] = set()

    def _emit_file(gi_path: Path, anchor: str) -> Iterator[tuple[str, str]]:
        if gi_path in seen_paths or not gi_path.is_file():
            return
        seen_paths.add(gi_path)
        try:
            text = gi_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        for line in text.splitlines():
            yield anchor, line

    # Root .gitignore + info/exclude first (anchor '').
    yield from _emit_file(repo / ".gitignore", "")
    yield from _emit_file(repo / ".git" / "info" / "exclude", "")

    # Nested: shallow to deep.
    for anchor in anchors[1:]:
        yield from _emit_file(repo / anchor / ".gitignore", anchor)


@lru_cache(maxsize=4096)
def _single_pattern_spec(pattern_body: str) -> pathspec.PathSpec:
    return pathspec.PathSpec.from_lines("gitignore", [pattern_body])


def is_ignored_by_gitignore(repo: Path, rel_posix: str) -> bool:
    """Return True if ``rel_posix`` (POSIX, relative to repo root) would be
    ignored by the aggregate gitignore rules that apply to that path.

    This mirrors git's "last match wins" semantics, including ``!`` negation,
    but evaluates against **tracked** paths (``git check-ignore`` would not
    flag them).
    """
    rel_posix = rel_posix.replace("\\", "/")
    last_ignored: bool | None = None
    for anchor, raw in _iter_gitignore_rule_lines(repo, rel_posix):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        negated = line.startswith("!")
        body = line[1:].strip() if negated else line
        if not body:
            continue
        suffix = _rel_suffix_under_anchor(rel_posix, anchor)
        if suffix is None:
            continue
        spec = _single_pattern_spec(body)
        if spec.match_file(suffix):
            last_ignored = not negated
    return bool(last_ignored)


def make_tracked_path_predicate(
    repo: Path,
    *,
    glob_keep: Callable[[str], bool],
    ignore_directories: Iterable[str],
    respect_gitignore: bool,
) -> Callable[[str], bool]:
    """Combine glob AND-filter, directory-prefix ignores, and gitignore rules.

    ``glob_keep`` is typically ``make_filter(patterns)`` from the CLI/config
    glob list. A path is kept iff ``glob_keep`` is True, it is not under any
    ``ignore_directories`` prefix, and (when ``respect_gitignore``) gitignore
    rules do not mark it ignored.
    """
    prefixes = [normalize_directory_prefix(p) for p in ignore_directories]

    def keep(rel_posix: str) -> bool:
        rel_posix = rel_posix.replace("\\", "/")
        if not glob_keep(rel_posix):
            return False
        if is_ignored_by_directory_prefixes(rel_posix, prefixes):
            return False
        if respect_gitignore and is_ignored_by_gitignore(repo, rel_posix):
            return False
        return True

    return keep
