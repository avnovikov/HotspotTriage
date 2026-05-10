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


def _repo_files_from_rows(rows: list[dict]) -> set[str]:
    """Repo-relative file paths behind block paths (``file::symbol``)."""
    return {
        str(r["path"]).split("::", 1)[0]
        for r in rows
        if not str(r["path"]).startswith("__")
    }


def _run(args: list[str]) -> subprocess.CompletedProcess:
    """Always pass --no-config so a developer's ~/.hotspottriage/config.yml
    cannot change the meaning of these end-to-end assertions."""
    return subprocess.run(
        [sys.executable, "-m", "hotspottriage", *args, "--no-config"],
        capture_output=True,
        text=True,
    )


def _run_with_repo_config(repo: Path, args: list[str]) -> subprocess.CompletedProcess:
    """Like a normal CLI run: merge ``<repo>/.hotspottriage/project.yml`` (no ``--no-config``)."""
    return subprocess.run(
        [sys.executable, "-m", "hotspottriage", str(repo), *args],
        capture_output=True,
        text=True,
    )


def _cli_json_envelope(stdout: str) -> dict:
    """CLI ``-f json`` emits an object aligned with MCP ``analyze`` (``results``, ``cache``, …)."""
    data = json.loads(stdout)
    assert isinstance(data, dict)
    assert "results" in data and isinstance(data["results"], list)
    assert "cache" in data and isinstance(data["cache"], dict)
    cache = data["cache"]
    for key in ("cache_file", "entries", "size_bytes"):
        assert key in cache
    return data


def _cli_json_rows(stdout: str) -> list[dict]:
    return _cli_json_envelope(stdout)["results"]


def test_cli_json_emits_all_metrics_including_per_sloc(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    r = _run([str(repo), "--no-similarity", "-f", "json"])
    assert r.returncode == 0, r.stderr
    env = _cli_json_envelope(r.stdout)
    rows = env["results"]
    assert isinstance(env.get("head_sha"), str) and len(env["head_sha"]) >= 7
    assert _repo_files_from_rows(rows) == {"a.py", "b.py", "c/d.py"}
    for row in rows:
        if str(row["path"]).startswith("__"):
            continue
        for col in ("path", *METRIC_COLS):
            assert col in row
        assert "proposed_model" in row and isinstance(row["proposed_model"], str)
        assert "rationale" in row and isinstance(row["rationale"], str)
        if row["sloc"] > 0:
            d = max(int(row["sloc"]), int(DEFAULTS["min_sloc_for_ratio"]))
            assert row["churn_per_sloc"] == row["churn"] / d
            assert row["decayed_churn_per_sloc"] == row["decayed_churn"] / d
        assert 0.0 <= float(row["score"]) <= 1.0
        assert isinstance(row.get("score_subscores"), dict)


def test_cli_score_picks_metrics_to_multiply(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    (repo / ".hotspottriage").mkdir()
    (repo / ".hotspottriage" / "project.yml").write_text(
        "score_aggregation:\n  enabled: false\n"
    )
    r = _run_with_repo_config(
        repo, ["--no-similarity", "-s", "churn,cyclomatic", "-f", "json"]
    )
    assert r.returncode == 0, r.stderr
    for row in _cli_json_rows(r.stdout):
        if str(row["path"]).startswith("__"):
            continue
        assert row["score"] == row["churn"] * row["cyclomatic"]


def test_cli_score_single_metric_sorts_by_that_metric(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    (repo / ".hotspottriage").mkdir()
    (repo / ".hotspottriage" / "project.yml").write_text(
        "score_aggregation:\n  enabled: false\n"
    )
    r = _run_with_repo_config(repo, ["--no-similarity", "-s", "churn", "-f", "json"])
    assert r.returncode == 0, r.stderr
    rows = _cli_json_rows(r.stdout)
    rows = [r for r in rows if not str(r["path"]).startswith("__")]
    # Sorted by score; with aggregation off and -s churn only, score equals churn.
    churns = [row["churn"] for row in rows]
    assert churns == sorted(churns, reverse=True)


def test_cli_score_rejects_bad_metric(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    r = _run([str(repo), "-s", "churn,bogus"])
    assert r.returncode == 1
    assert "unknown score metric" in r.stderr


def test_cli_csv_has_all_metric_headers(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    r = _run([str(repo), "--no-similarity", "-f", "csv"])
    assert r.returncode == 0, r.stderr
    reader = csv.DictReader(io.StringIO(r.stdout))
    assert reader.fieldnames == ["path", *METRIC_COLS]
    rows = list(reader)
    assert len(rows) >= 3
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
    rows = _cli_json_rows(r.stdout)
    paths = [row["path"] for row in rows]
    assert all("::" in p for p in paths)
    assert any(p.startswith("mod.py::") for p in paths)


def test_cli_blocks_json_stdout_is_valid_json_with_mcp_style_fields(tmp_path: Path):
    """Regression for #155: no trailing prose on stdout; agent fields live in each row."""
    repo = build_block_repo(tmp_path / "block_r_json155")
    r = _run([str(repo), "--blocks", "--no-similarity", "-f", "json"])
    assert r.returncode == 0, r.stderr
    rows = _cli_json_rows(r.stdout)
    assert rows
    for row in rows:
        assert "proposed_model" in row and isinstance(row["proposed_model"], str)
        assert "rationale" in row and isinstance(row["rationale"], str)
        assert "score_narrative" in row and isinstance(row["score_narrative"], str)


def test_cli_block_json_score_explanation_items_never_include_raw(tmp_path: Path):
    """Contract: CLI block JSON matches MCP full rows—no raw in score_explanation."""
    repo = build_block_repo(tmp_path / "block_r_rawcheck")
    r = _run(
        [str(repo), "--blocks", "--no-similarity", "-f", "json", "-l", "8"]
    )
    assert r.returncode == 0, r.stderr
    rows = _cli_json_rows(r.stdout)
    assert rows
    for row in rows:
        expl = row.get("score_explanation")
        if expl is None:
            continue
        if isinstance(expl, str):
            expl = json.loads(expl)
        for item in expl:
            assert isinstance(item, dict)
            assert "raw" not in item


def test_cli_filter_excludes(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    r = _run([str(repo), "--no-similarity", "--filter", "!c/**", "-f", "json"])
    assert r.returncode == 0, r.stderr
    assert _repo_files_from_rows(_cli_json_rows(r.stdout)) == {"a.py", "b.py"}


def test_cli_limit(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    r = _run([str(repo), "--no-similarity", "-f", "json", "-l", "1"])
    assert r.returncode == 0, r.stderr
    assert len(_cli_json_rows(r.stdout)) == 1


def test_cli_sort_by_file(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    r = _run([str(repo), "--no-similarity", "--sort", "file", "-f", "json"])
    assert r.returncode == 0, r.stderr
    paths = [row["path"] for row in _cli_json_rows(r.stdout)]
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
    r = _run([str(repo), "--no-default-filter", "--no-similarity", "-f", "json"])
    assert r.returncode == 0, r.stderr
    tracked = subprocess.run(
        ["git", "-C", str(repo), "ls-files"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    assert "README.md" in tracked
    assert _cli_json_rows(r.stdout)


def test_cli_project_config_changes_default_format(tmp_path: Path):
    """A `<repo>/.hotspottriage/project.yml` should change the default output
    format end-to-end (no --no-config; CLI does not pass -f)."""
    repo = build_repo(tmp_path / "r")
    cfg_dir = repo / ".hotspottriage"
    cfg_dir.mkdir()
    (cfg_dir / "project.yml").write_text(
        "format: json\nsimilarity_enabled: false\n"
    )
    r = subprocess.run(
        [sys.executable, "-m", "hotspottriage", str(repo)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    rows = _cli_json_rows(r.stdout)
    assert rows


def test_cli_dashboard_config_patch_matches_mcp_stack(tmp_path: Path):
    """Without ``--no-config``, CLI merges ``dashboard_config_patch.yml`` like
    MCP local ``analyze`` (after project YAML, before CLI flags)."""
    repo = build_block_repo(tmp_path / "patch_r")
    cfg_dir = repo / ".hotspottriage"
    cfg_dir.mkdir(exist_ok=True)
    (cfg_dir / "dashboard_config_patch.yml").write_text(
        """
score_aggregation:
  final_weights:
    complexity_burden: 0.50
    churn_burden: 0.20
    maintainability_burden: 0.15
    smell_burden: 0.10
    similarity_burden: 0.05
""".strip()
        + "\n"
    )
    r_default = _run([str(repo), "--no-similarity", "-f", "json", "-l", "1"])
    r_patched = subprocess.run(
        [
            sys.executable,
            "-m",
            "hotspottriage",
            str(repo),
            "--no-similarity",
            "-f",
            "json",
            "-l",
            "1",
        ],
        capture_output=True,
        text=True,
    )
    assert r_default.returncode == 0, r_default.stderr
    assert r_patched.returncode == 0, r_patched.stderr
    row_d = _cli_json_rows(r_default.stdout)[0]
    row_p = _cli_json_rows(r_patched.stdout)[0]
    assert row_d["path"] == row_p["path"]
    expl_d = row_d["score_explanation"]
    expl_p = row_p["score_explanation"]
    if isinstance(expl_d, str):
        expl_d = json.loads(expl_d)
    if isinstance(expl_p, str):
        expl_p = json.loads(expl_p)
    fw_d = next(x["final_weight"] for x in expl_d if x["driver"] == "complexity")
    fw_p = next(x["final_weight"] for x in expl_p if x["driver"] == "complexity")
    # DEFAULTS with similarity off: 0.30 / (0.30 + 0.25 + 0.20 + 0.15) ≈ 0.3333
    assert abs(fw_d - (0.30 / 0.90)) < 1e-4
    # Patched 0.50 among the same four non-similarity burdens: 0.50 / 0.95
    assert abs(fw_p - (0.50 / 0.95)) < 1e-4


def test_cli_explicit_config_file(tmp_path: Path):
    """`--config PATH` is the highest-precedence file layer (still beaten
    only by CLI flags)."""
    repo = build_repo(tmp_path / "r")
    cfg = tmp_path / "extra.yml"
    cfg.write_text("format: csv\n")
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "hotspottriage",
            str(repo),
            "--no-similarity",
            "--config",
            str(cfg),
        ],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout.lstrip().startswith("path,")  # CSV header


def test_cli_invalid_config_value_reported(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    cfg = tmp_path / "bad.yml"
    cfg.write_text("format: yaml\n")
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "hotspottriage",
            str(repo),
            "--no-similarity",
            "--config",
            str(cfg),
        ],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 1
    assert "unknown format" in r.stderr


def test_cli_respects_root_gitignore_for_tracked_files(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    (repo / ".gitignore").write_text("b.py\n")
    subprocess.run(["git", "-C", str(repo), "add", ".gitignore"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "gitignore"], check=True)

    r = _run([str(repo), "--no-similarity", "-f", "json"])
    assert r.returncode == 0, r.stderr
    assert _repo_files_from_rows(_cli_json_rows(r.stdout)) == {"a.py", "c/d.py"}


def test_cli_ignore_dir_excludes_prefix(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    r = _run([str(repo), "--no-similarity", "--ignore-dir", "c", "-f", "json"])
    assert r.returncode == 0, r.stderr
    assert _repo_files_from_rows(_cli_json_rows(r.stdout)) == {"a.py", "b.py"}


def test_cli_no_respect_gitignore_includes_tracked_matches(tmp_path: Path):
    repo = build_repo(tmp_path / "r")
    (repo / ".gitignore").write_text("b.py\n")
    subprocess.run(["git", "-C", str(repo), "add", ".gitignore"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "gitignore"], check=True)

    r = _run([str(repo), "--no-similarity", "--no-respect-gitignore", "-f", "json"])
    assert r.returncode == 0, r.stderr
    assert _repo_files_from_rows(_cli_json_rows(r.stdout)) == {"a.py", "b.py", "c/d.py"}


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
