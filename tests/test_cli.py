"""End-to-end CLI tests against a generated fixture repo."""
import csv
import io
import json
import subprocess
import sys
from pathlib import Path

from hotspottriage.config import DEFAULTS
from hotspottriage.output import display_headers

from tests.fixtures.build_repo import build_repo
from tests.fixtures.build_block_repo import build_block_repo


METRIC_COLS = tuple(c for c in display_headers(DEFAULTS) if c != "path")


def _run(args: list[str]) -> subprocess.CompletedProcess:
    """Always pass --no-config so a developer's ~/.hotspottriage/config.yml
    cannot change the meaning of these end-to-end assertions."""
    return subprocess.run(
        [sys.executable, "-m", "hotspottriage", *args, "--no-config"],
        capture_output=True,
        text=True,
    )


def test_cli_json_emits_all_metrics_including_per_sloc(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    r = _run([str(repo), "-f", "json"])
    assert r.returncode == 0, r.stderr
    rows = json.loads(r.stdout)
    assert {row["path"] for row in rows} == {"a.py", "b.py", "c/d.py"}
    for row in rows:
        for col in ("path", *METRIC_COLS):
            assert col in row
        if row["sloc"] > 0:
            assert row["churn_per_sloc"] == row["churn"] / row["sloc"]
            assert row["decayed_churn_per_sloc"] == row["decayed_churn"] / row["sloc"]
        # Default score = decayed_churn_per_sloc × cyclomatic.
        assert row["score"] == row["decayed_churn_per_sloc"] * row["cyclomatic"]


def test_cli_score_picks_metrics_to_multiply(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    r = _run([str(repo), "-s", "churn,cyclomatic", "-f", "json"])
    assert r.returncode == 0, r.stderr
    for row in json.loads(r.stdout):
        assert row["score"] == row["churn"] * row["cyclomatic"]


def test_cli_score_single_metric_sorts_by_that_metric(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    r = _run([str(repo), "-s", "churn", "-f", "json"])
    assert r.returncode == 0, r.stderr
    rows = json.loads(r.stdout)
    # Result should be sorted desc by raw churn (lines added+deleted).
    churns = [row["churn"] for row in rows]
    assert churns == sorted(churns, reverse=True)


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
        smells = json.loads(row["smells"])
        assert isinstance(smells, dict)
        assert all(isinstance(k, str) and isinstance(v, int) for k, v in smells.items())
        int_cols = (
            "sloc",
            "cyclomatic",
            "halstead",
            "maintainability",
            "churn",
            "smell_count",
            "match_count",
        )
        for col in int_cols:
            int(row[col])
        for col in METRIC_COLS:
            if col in int_cols or col in (
                "smells",
                "similarity_band",
                "score_band",
                "score_subscores",
                "score_explanation",
                "score_narrative",
            ):
                continue
            if col == "score_driver":
                assert isinstance(row[col], str)
                continue
            float(row[col])


def test_cli_blocks_shorthand_runs_block_granularity(tmp_path: Path):
    repo = build_block_repo(tmp_path / "block_r")
    r = _run([str(repo), "--blocks", "-f", "json"])
    assert r.returncode == 0, r.stderr
    rows = json.loads(r.stdout)
    paths = [row["path"] for row in rows]
    assert all("::" in p for p in paths)
    assert any(p.startswith("mod.py::") for p in paths)


def test_cli_blocks_conflicts_with_granularity_file(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    r = _run([str(repo), "--blocks", "--granularity", "file", "-f", "json"])
    assert r.returncode == 1
    assert "cannot combine" in r.stderr


def test_cli_directories_aggregates(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    r = _run([str(repo), "-d", "-f", "json"])
    assert r.returncode == 0, r.stderr
    rows = json.loads(r.stdout)
    assert {row["path"] for row in rows} == {"c"}
    row = rows[0]
    if row["sloc"] > 0:
        assert row["churn_per_sloc"] == row["churn"] / row["sloc"]


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


def test_cli_project_config_changes_default_format(tmp_path: Path):
    """A `<repo>/.hotspottriage/project.yml` should change the default output
    format end-to-end (no --no-config; CLI does not pass -f)."""
    repo = build_repo(tmp_path / "r")
    cfg_dir = repo / ".hotspottriage"
    cfg_dir.mkdir()
    (cfg_dir / "project.yml").write_text("format: json\n")
    r = subprocess.run(
        [sys.executable, "-m", "hotspottriage", str(repo)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    rows = json.loads(r.stdout)
    assert rows


def test_cli_explicit_config_file(tmp_path: Path):
    """`--config PATH` is the highest-precedence file layer (still beaten
    only by CLI flags)."""
    repo = build_repo(tmp_path / "r")
    cfg = tmp_path / "extra.yml"
    cfg.write_text("format: csv\n")
    r = subprocess.run(
        [sys.executable, "-m", "hotspottriage", str(repo), "--config", str(cfg)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout.lstrip().startswith("path,")  # CSV header


def test_cli_invalid_config_value_reported(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    cfg = tmp_path / "bad.yml"
    cfg.write_text("format: yaml\n")
    r = subprocess.run(
        [sys.executable, "-m", "hotspottriage", str(repo), "--config", str(cfg)],
        capture_output=True, text=True,
    )
    assert r.returncode == 1
    assert "unknown format" in r.stderr


def test_cli_respects_root_gitignore_for_tracked_files(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    (repo / ".gitignore").write_text("b.py\n")
    subprocess.run(["git", "-C", str(repo), "add", ".gitignore"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "gitignore"], check=True)

    r = _run([str(repo), "-f", "json"])
    assert r.returncode == 0, r.stderr
    paths = {row["path"] for row in json.loads(r.stdout)}
    assert paths == {"a.py", "c/d.py"}


def test_cli_ignore_dir_excludes_prefix(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    r = _run([str(repo), "--ignore-dir", "c", "-f", "json"])
    assert r.returncode == 0, r.stderr
    paths = {row["path"] for row in json.loads(r.stdout)}
    assert paths == {"a.py", "b.py"}


def test_cli_no_respect_gitignore_includes_tracked_matches(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    (repo / ".gitignore").write_text("b.py\n")
    subprocess.run(["git", "-C", str(repo), "add", ".gitignore"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "gitignore"], check=True)

    r = _run([str(repo), "--no-respect-gitignore", "-f", "json"])
    assert r.returncode == 0, r.stderr
    paths = {row["path"] for row in json.loads(r.stdout)}
    assert paths == {"a.py", "b.py", "c/d.py"}


def test_cli_start_mcp_server_rewrites_argv_and_delegates(monkeypatch):
    """`hotspottriage start-mcp-server` matches Serena's `serena start-mcp-server` layout."""
    seen: dict[str, list[str]] = {}

    def _capture_mcp_main() -> None:
        seen["argv"] = sys.argv.copy()

    monkeypatch.setattr("hotspottriage.mcp_server.main", _capture_mcp_main)
    monkeypatch.setattr(
        sys,
        "argv",
        ["/x/venv/bin/hotspottriage", "start-mcp-server", "--no-dashboard"],
    )
    from hotspottriage import cli

    assert cli.main() == 0
    assert seen["argv"] == ["/x/venv/bin/hotspottriage", "--no-dashboard"]
