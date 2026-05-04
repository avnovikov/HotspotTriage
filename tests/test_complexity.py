from pathlib import Path
from textwrap import dedent

import pytest

from code_complexity_py import complexity


@pytest.fixture
def py_file(tmp_path: Path) -> Path:
    src = dedent(
        """
        def f(x):
            if x > 0:
                for i in range(x):
                    if i % 2 == 0:
                        print(i)
            elif x < 0:
                return -1
            else:
                return 0
            return x
        """
    )
    p = tmp_path / "sample.py"
    p.write_text(src)
    return p


def test_cyclomatic_matches_hand_count(py_file: Path):
    # f has: 1 (base) + if + for + nested if + elif + else handled as branches.
    # radon's count for this body is 5; we assert that exactly.
    assert complexity.compute(py_file, "cyclomatic") == 5


def test_sloc_counts_source_lines(py_file: Path):
    # 10 source lines (def + 9 body lines), no blanks/comments inside.
    assert complexity.compute(py_file, "sloc") == 10


def test_halstead_returns_positive_int(py_file: Path):
    v = complexity.compute(py_file, "halstead")
    assert isinstance(v, int) and v > 0


def test_maintainability_returns_inverted_score(py_file: Path):
    v = complexity.compute(py_file, "maintainability")
    # Inverted MI: 0..100 where higher = worse.
    assert isinstance(v, int) and 0 <= v <= 100


def test_syntax_error_returns_zero_and_warns(tmp_path: Path, capsys: pytest.CaptureFixture):
    bad = tmp_path / "bad.py"
    bad.write_text("def (:\n")
    assert complexity.compute(bad, "cyclomatic") == 0
    assert "cannot analyze" in capsys.readouterr().err


def test_unknown_strategy_raises(py_file: Path):
    with pytest.raises(ValueError, match="unknown strategy"):
        complexity.compute(py_file, "nope")
