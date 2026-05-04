from code_complexity_py.filtering import make_filter


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
