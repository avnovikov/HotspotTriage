import subprocess
from pathlib import Path

import pytest

from hotspottriage.filtering import (
    is_ignored_by_directory_prefixes,
    is_ignored_by_gitignore,
    make_filter,
    make_tracked_path_predicate,
    normalize_directory_prefix,
)
from tests.fixtures.build_repo import build_repo


def test_no_patterns_keeps_everything():
    keep = make_filter([])
    assert keep("a.py")
    assert keep("src/x/y.py")


def test_single_recursive_glob():
    keep = make_filter(["**/*.py"])
    assert keep("a.py")
    assert keep("src/x/y.py")
    assert not keep("a.js")
    assert not keep("README.md")


def test_top_level_only_glob():
    # `*.py` is a single-segment glob; pathspec gitwildmatch interprets a bare
    # filename without slashes as matching at any depth, like gitignore. To
    # match top-level only, callers should prefix with `/` or use an explicit
    # path. This test pins the behaviour we ship with.
    keep = make_filter(["*.py"])
    assert keep("a.py")
    assert keep("src/x.py")  # gitignore-style: bare name matches everywhere


def test_and_semantics_with_negation():
    keep = make_filter(["src/**", "!src/front/**"])
    assert keep("src/foo.py")
    assert keep("src/lib/bar.py")
    assert not keep("src/front/x.py")
    assert not keep("README.md")  # fails first pattern


def test_multiple_positive_patterns_must_all_match():
    keep = make_filter(["src/**", "**/*.py"])
    assert keep("src/x.py")
    assert not keep("src/x.txt")  # fails 2nd pattern
    assert not keep("docs/x.py")  # fails 1st pattern


# --- directory prefixes ---------------------------------------------------


def test_normalize_directory_prefix_strips_slashes():
    assert normalize_directory_prefix(" /vendor/ ") == "vendor"


def test_normalize_directory_prefix_rejects_dotdot():
    with pytest.raises(ValueError, match=r"\.\."):
        normalize_directory_prefix("foo/../bar")


def test_is_ignored_by_directory_prefixes():
    assert is_ignored_by_directory_prefixes("vendor/pkg/x.py", ["vendor"])
    assert is_ignored_by_directory_prefixes("vendor", ["vendor"])
    assert not is_ignored_by_directory_prefixes("src/vendor/x.py", ["vendor"])


# --- gitignore on tracked paths -------------------------------------------


def test_gitignore_excludes_tracked_file(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    (repo / ".gitignore").write_text("b.py\n")
    subprocess.run(["git", "-C", str(repo), "add", ".gitignore"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "gitignore"], check=True)

    assert is_ignored_by_gitignore(repo, "b.py")
    assert not is_ignored_by_gitignore(repo, "a.py")


def test_nested_gitignore_applies_to_suffix(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    sub = repo / "pkg"
    sub.mkdir()
    (sub / "hidden.py").write_text("x = 1\n")
    subprocess.run(["git", "-C", str(repo), "add", "pkg/hidden.py"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "pkg"], check=True)

    (sub / ".gitignore").write_text("hidden.py\n")
    subprocess.run(["git", "-C", str(repo), "add", "pkg/.gitignore"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "nested gi"], check=True)

    assert is_ignored_by_gitignore(repo, "pkg/hidden.py")


def test_make_tracked_path_predicate_combines_globs_and_gitignore(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    (repo / ".gitignore").write_text("b.py\n")
    subprocess.run(["git", "-C", str(repo), "add", ".gitignore"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "gitignore"], check=True)

    glob_keep = make_filter(["**/*.py"])
    keep = make_tracked_path_predicate(
        repo,
        glob_keep=glob_keep,
        ignore_directories=["c"],
        respect_gitignore=True,
    )
    assert keep("a.py")
    assert not keep("b.py")  # gitignore
    assert not keep("c/d.py")  # directory prefix
