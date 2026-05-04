"""End-to-end CLI tests against a generated fixture repo."""
import csv
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.fixtures.build_repo import build_repo


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "code_complexity_py", *args],
        capture_output=True,
        text=True,
    )


def test_cli_json_default_filter(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    r = _run([str(repo), "-cs", "cyclomatic", "-f", "json", "-s", "score"])
    assert r.returncode == 0, r.stderr
    rows = json.loads(r.stdout)
    by = {row["path"]: row for row in rows}
    assert set(by) == {"a.py", "b.py", "c/d.py"}
    assert by["c/d.py"]["complexity"] == 3
    assert by["c/d.py"]["churn"] == 2
    assert by["c/d.py"]["score"] == 6
    # Sort: descending by score. a.py (cc=2, churn=4 -> score=8) > c/d.py (score=6) > b.py (score=1).
    assert [row["path"] for row in rows] == ["a.py", "c/d.py", "b.py"]


def test_cli_csv_is_real_csv(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    r = _run([str(repo), "-f", "csv"])
    assert r.returncode == 0, r.stderr
    reader = csv.DictReader(io.StringIO(r.stdout))
    rows = list(reader)
    assert reader.fieldnames == ["path", "complexity", "churn", "score"]
    assert len(rows) == 3
    # All-numeric columns should parse back as ints.
    for row in rows:
        int(row["complexity"]); int(row["churn"]); int(row["score"])


def test_cli_table_renders_pipes(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    r = _run([str(repo), "-f", "table"])
    assert r.returncode == 0, r.stderr
    assert "path" in r.stdout and "score" in r.stdout
    assert "|" in r.stdout  # github-flavoured tabulate uses pipes


def test_cli_directories_aggregates(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    r = _run([str(repo), "-d", "-f", "json"])
    assert r.returncode == 0, r.stderr
    rows = json.loads(r.stdout)
    paths = {row["path"] for row in rows}
    assert paths == {"c"}  # only c/d.py has a parent dir; a.py & b.py are top-level


def test_cli_filter_excludes(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    r = _run([str(repo), "--filter", "!c/**", "-f", "json"])
    assert r.returncode == 0, r.stderr
    rows = json.loads(r.stdout)
    assert {row["path"] for row in rows} == {"a.py", "b.py"}


def test_cli_limit(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    r = _run([str(repo), "-f", "json", "-l", "1"])
    assert r.returncode == 0, r.stderr
    rows = json.loads(r.stdout)
    assert len(rows) == 1


def test_cli_rejects_non_git(tmp_path: Path):
    (tmp_path / "plain").mkdir()
    r = _run([str(tmp_path / "plain")])
    assert r.returncode == 1
    assert "not a git repository" in r.stderr


def test_cli_no_default_filter_includes_non_py(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    # Add a tracked non-Python file.
    (repo / "README.md").write_text("hello\n")
    subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "readme"], check=True)
    r = _run([str(repo), "--no-default-filter", "-cs", "sloc", "-f", "json"])
    assert r.returncode == 0, r.stderr
    paths = {row["path"] for row in json.loads(r.stdout)}
    assert "README.md" in paths
