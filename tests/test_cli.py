"""End-to-end CLI tests against a generated fixture repo."""
import csv
import io
import json
import subprocess
import sys
from pathlib import Path

from tests.fixtures.build_repo import build_repo


METRIC_COLS = ("sloc", "cyclomatic", "halstead", "maintainability", "churn", "score")


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "code_complexity_py", *args],
        capture_output=True,
        text=True,
    )


def test_cli_json_emits_all_metrics(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    r = _run([str(repo), "-f", "json"])
    assert r.returncode == 0, r.stderr
    rows = json.loads(r.stdout)
    assert {row["path"] for row in rows} == {"a.py", "b.py", "c/d.py"}
    for row in rows:
        for col in ("path", *METRIC_COLS):
            assert col in row
    by = {row["path"]: row for row in rows}
    # Default score = churn × cyclomatic.
    assert by["c/d.py"]["cyclomatic"] == 3
    assert by["c/d.py"]["churn"] == 2
    assert by["c/d.py"]["score"] == 6


def test_cli_score_picks_metrics_to_multiply(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    r = _run([str(repo), "-s", "churn,sloc", "-f", "json"])
    assert r.returncode == 0, r.stderr
    by = {row["path"]: row for row in json.loads(r.stdout)}
    for row in by.values():
        assert row["score"] == row["churn"] * row["sloc"]


def test_cli_score_single_metric_sorts_by_that_metric(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    r = _run([str(repo), "-s", "churn", "-f", "json"])
    assert r.returncode == 0, r.stderr
    rows = json.loads(r.stdout)
    # a.py has churn 4, c/d.py has 2, b.py has 1 → that's the order.
    assert [row["path"] for row in rows] == ["a.py", "c/d.py", "b.py"]


def test_cli_score_three_metrics(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    r = _run([str(repo), "-s", "churn,cyclomatic,sloc", "-f", "json"])
    assert r.returncode == 0, r.stderr
    by = {row["path"]: row for row in json.loads(r.stdout)}
    for row in by.values():
        assert row["score"] == row["churn"] * row["cyclomatic"] * row["sloc"]


def test_cli_score_rejects_bad_metric(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    r = _run([str(repo), "-s", "churn,bogus"])
    assert r.returncode == 1
    assert "unknown score metric" in r.stderr


def test_cli_csv_has_all_metric_headers(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    r = _run([str(repo), "-f", "csv"])
    assert r.returncode == 0, r.stderr
    reader = csv.DictReader(io.StringIO(r.stdout))
    assert reader.fieldnames == ["path", *METRIC_COLS]
    rows = list(reader)
    assert len(rows) == 3
    for row in rows:
        for col in METRIC_COLS:
            int(row[col])  # parses cleanly


def test_cli_directories_aggregates(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    r = _run([str(repo), "-d", "-f", "json"])
    assert r.returncode == 0, r.stderr
    rows = json.loads(r.stdout)
    assert {row["path"] for row in rows} == {"c"}
    # c contains only c/d.py with cyclomatic=3, churn=2.
    assert rows[0]["cyclomatic"] == 3 and rows[0]["churn"] == 2
    assert rows[0]["score"] == 6  # default churn × cyclomatic


def test_cli_filter_excludes(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    r = _run([str(repo), "--filter", "!c/**", "-f", "json"])
    assert r.returncode == 0, r.stderr
    paths = {row["path"] for row in json.loads(r.stdout)}
    assert paths == {"a.py", "b.py"}


def test_cli_limit(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    r = _run([str(repo), "-f", "json", "-l", "1"])
    assert r.returncode == 0, r.stderr
    assert len(json.loads(r.stdout)) == 1


def test_cli_sort_by_file(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    r = _run([str(repo), "--sort", "file", "-f", "json"])
    assert r.returncode == 0, r.stderr
    paths = [row["path"] for row in json.loads(r.stdout)]
    assert paths == sorted(paths)


def test_cli_rejects_non_git(tmp_path: Path):
    (tmp_path / "plain").mkdir()
    r = _run([str(tmp_path / "plain")])
    assert r.returncode == 1
    assert "not a git repository" in r.stderr


def test_cli_no_default_filter_includes_non_py(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    (repo / "README.md").write_text("hello\n")
    subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "readme"], check=True)
    r = _run([str(repo), "--no-default-filter", "-f", "json"])
    assert r.returncode == 0, r.stderr
    paths = {row["path"] for row in json.loads(r.stdout)}
    assert "README.md" in paths
