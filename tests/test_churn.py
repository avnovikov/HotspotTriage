from pathlib import Path
import subprocess

from code_complexity_py.churn import compute_churn
from tests.fixtures.build_repo import build_repo


def _expected_churn_via_git(repo: Path) -> dict[str, int]:
    """Recompute the same numstat sum via a separate git invocation, to assert
    the implementation matches what git itself reports."""
    out = subprocess.run(
        ["git", "-C", str(repo), "log", "--format=", "--numstat"],
        check=True, capture_output=True, text=True,
    ).stdout
    counts: dict[str, int] = {}
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        a, d, p = parts
        if a == "-" or d == "-":
            continue
        counts[p] = counts.get(p, 0) + int(a) + int(d)
    return counts


def test_churn_sums_lines_added_and_deleted(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    churn = compute_churn(repo)
    assert churn == _expected_churn_via_git(repo)
    # All three fixture files should have non-zero churn (each had at least one commit).
    assert churn["a.py"] > 0 and churn["b.py"] > 0 and churn["c/d.py"] > 0
    # a.py was edited in 4 commits and accumulates more changes than b.py (1 commit).
    assert churn["a.py"] > churn["b.py"]


def test_churn_skips_binary_files(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    # Add a binary file.
    (repo / "x.bin").write_bytes(b"\x00\x01\x02\x03" * 32)
    subprocess.run(["git", "-C", str(repo), "add", "x.bin"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "bin"], check=True)
    churn = compute_churn(repo)
    assert "x.bin" not in churn


def test_churn_since_filters_recent_commits(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    churn = compute_churn(repo, since="2099-01-01")
    assert churn == {}
