from pathlib import Path

from code_complexity_py.churn import compute_churn
from tests.fixtures.build_repo import build_repo


def test_churn_counts_commit_touches(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    churn = compute_churn(repo)
    assert churn == {"a.py": 4, "b.py": 1, "c/d.py": 2}


def test_churn_since_filters_recent_commits(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    # Far-future date — should yield no commits.
    churn = compute_churn(repo, since="2099-01-01")
    assert churn == {}
