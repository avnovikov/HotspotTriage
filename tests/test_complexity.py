from pathlib import Path
from textwrap import dedent

import pytest

from hotspottriage import complexity


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


def test_compute_all_returns_every_metric(py_file: Path):
    out = complexity.compute_all(py_file)
    assert set(out) == set(complexity.METRICS)
    assert out["cyclomatic"] == 5
    assert out["sloc"] == 10
    assert out["halstead"] > 0
    assert 0 <= out["maintainability"] <= 100


def test_syntax_error_returns_zeros_and_warns(tmp_path: Path, capsys: pytest.CaptureFixture):
    bad = tmp_path / "bad.py"
    bad.write_text("def (:\n")
    out = complexity.compute_all(bad)
    assert all(v == 0 for v in out.values())
    assert "cannot analyze" in capsys.readouterr().err


def test_unreadable_file_returns_zeros(tmp_path: Path, capsys: pytest.CaptureFixture):
    out = complexity.compute_all(tmp_path / "does_not_exist.py")
    assert all(v == 0 for v in out.values())
    assert "cannot read" in capsys.readouterr().err
