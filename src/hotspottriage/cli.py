"""CLI entry point. See `hotspottriage --help` for usage.

Settings flow through three layers (last wins): code DEFAULTS, the
`~/.hotspottriage/...` + `<repo>/.hotspottriage/...` config files
(see `config.py`), and CLI flags. The argparse defaults are deliberately
`None` sentinels so the merge layer can tell "user passed this flag" from
"user did not".

The `init` subcommand is detected manually before argparse is invoked so
its parser does not interfere with the analyze command's positional
`target` argument (subparsers consume the first positional and would
reject any non-`init` string).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Callable
from pathlib import Path

from hotspottriage import cache as _block_cache
from hotspottriage import config as _config
from hotspottriage import discovery, filtering, output, progress_report, stats
from hotspottriage.revision_cache import RevisionCacheManager
from hotspottriage import score_metrics as _score_metrics


def _want_progress(cfg: dict) -> bool:
    explicit = cfg.get("progress")
    if explicit is True:
        return True
    if explicit is False:
        return False
    return progress_report.stderr_progress_enabled()


def _build_analyze_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="hotspottriage",
        description=(
            "Rank Python code at block granularity: one row per function/method "
            "(sloc, cyclomatic, halstead, maintainability, churn, smells, similarity). "
            "First run is slower (per-block git churn); results are cached under "
            ".hotspottriage/cache/. "
            "Use `hotspottriage init --global|--project` to scaffold a config file."
        ),
    )
    p.add_argument("target", help="path to a local git repo, or a remote git URL")
    p.add_argument(
        "--filter",
        default=None,
        help=(
            "comma-separated gitignore-style patterns (AND with each other and the "
            "default filter unless --no-default-filter; '!' negates). MCP analyze "
            "uses OR for two+ all-literal paths only — see docs/agent-hotspottriage-score-check.md"
        ),
    )
    p.add_argument(
        "--no-default-filter",
        dest="no_default_filter",
        action="store_true",
        default=None,
        help=(
            "disable the implicit default filter "
            f"(default: {_config.DEFAULTS['default_filter']})"
        ),
    )
    p.add_argument(
        "-s",
        "--score",
        default=None,
        help=(
            "comma-separated score_metrics list (config + sorting); with the default "
            "score_aggregation recipe the composite 0–1 score uses all burdens — "
            "see score_aggregation in project.yml. When aggregation is disabled, "
            "the row score is the product of these metrics. "
            f"Choose from: {', '.join(_score_metrics.SCORE_METRICS)}. "
            f"Default: {','.join(_config.DEFAULTS['score_metrics'])}"
        ),
    )
    p.add_argument("-f", "--format", choices=output.FORMATS, default=None)
    p.add_argument("-l", "--limit", type=int, default=None)
    p.add_argument("-i", "--since", default=None)
    p.add_argument("-u", "--until", default=None)
    p.add_argument("--sort", choices=_score_metrics.SORT_KEYS, default=None)
    p.add_argument(
        "-B",
        "--blocks",
        action="store_true",
        default=None,
        help=(
            "no-op: retained for scripts; the CLI always runs block-level analysis."
        ),
    )
    p.add_argument(
        "--ignore-dir",
        dest="ignore_dir",
        action="append",
        default=None,
        metavar="PREFIX",
        help=(
            "exclude tracked paths under this POSIX directory prefix "
            "(repeatable); merged with ignore_directories from config"
        ),
    )
    p.add_argument(
        "--no-respect-gitignore",
        dest="no_respect_gitignore",
        action="store_true",
        default=None,
        help=(
            "do not apply .gitignore, nested .gitignore, or .git/info/exclude "
            "rules when filtering tracked paths"
        ),
    )
    p.add_argument(
        "--config",
        type=Path,
        default=None,
        help="path to an additional YAML config file applied after the standard layers",
    )
    p.add_argument(
        "--no-config",
        action="store_true",
        help="ignore all config files; use built-in defaults plus CLI flags only",
    )
    prog = p.add_mutually_exclusive_group()
    prog.add_argument(
        "--progress",
        dest="progress",
        action="store_true",
        default=None,
        help="show progress on stderr (overrides config; useful for long runs)",
    )
    prog.add_argument(
        "--no-progress",
        dest="no_progress",
        action="store_true",
        default=None,
        help="disable progress output",
    )
    sim = p.add_mutually_exclusive_group()
    sim.add_argument(
        "--similarity",
        dest="similarity",
        action="store_true",
        default=None,
        help=(
            "force DeepCSIM block similarity on (default is already on for block runs; "
            "overrides config similarity_enabled: false)"
        ),
    )
    sim.add_argument(
        "--no-similarity",
        dest="no_similarity",
        action="store_true",
        default=None,
        help="disable DeepCSIM block similarity (overrides config defaults)",
    )
    return p


def _build_init_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="hotspottriage init",
        description=(
            "Scaffold a HotspotTriage config file. Use --global to write "
            "~/.hotspottriage/config.yml, or --project to write "
            "<target>/.hotspottriage/project.yml plus a gitignored "
            "project.local.yml override."
        ),
    )
    scope = p.add_mutually_exclusive_group(required=True)
    scope.add_argument(
        "--global",
        dest="global_scope",
        action="store_true",
        help="write the global config at ~/.hotspottriage/config.yml",
    )
    scope.add_argument(
        "--project",
        dest="project_scope",
        action="store_true",
        help="write the project config under <target>/.hotspottriage/",
    )
    p.add_argument(
        "target",
        nargs="?",
        default=".",
        help="repo root for --project scope (default: current directory)",
    )
    return p


def _run_init(argv: list[str]) -> int:
    args = _build_init_parser().parse_args(argv)
    try:
        if args.global_scope:
            written = _config.init_config("global")
        else:
            target = Path(args.target).resolve()
            written = _config.init_config("project", target)
    except (FileExistsError, NotADirectoryError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"wrote {written}")
    return 0


def _resolve_config(args: argparse.Namespace, target_path: Path | None) -> dict:
    """Build merged config for ``analyze``, aligned with MCP local ``analyze``.

    Uses ``load_config(..., use_global=False)`` plus
    ``merge_dashboard_config_patch`` so CLI scores match MCP for the same repo
    (skips ``~/.hotspottriage/config.yml``; still honors project YAML,
    ``--config``, dashboard patch, then CLI flags).
    """
    if args.no_config:
        merged = _config.load_config(
            target_path=None, use_global=False, use_project=False
        )
    else:
        assert target_path is not None, "analyze always resolves a repo path"
        merged = _config.load_analyze_config_for_local_repo(
            target_path,
            explicit=args.config,
        )
    merged = _config.apply_cli_overrides(merged, args)
    if getattr(args, "progress", None):
        merged["progress"] = True
    if getattr(args, "no_progress", None):
        merged["progress"] = False
    if getattr(args, "similarity", None):
        merged["similarity_enabled"] = True
    if getattr(args, "no_similarity", None):
        merged["similarity_enabled"] = False
    # CLI always runs the block pipeline (per-function/method rows). File-level
    # analysis remains available via the library and other surfaces.
    merged["granularity"] = "block"
    _config.validate(merged)
    return merged


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # Serena-style MCP entry: `hotspottriage start-mcp-server` (keeps `hotspottriage-mcp` as an alias).
    if argv and argv[0] == "start-mcp-server":
        sys.argv = [sys.argv[0], *argv[1:]]
        from hotspottriage import mcp_server as _mcp_server

        _mcp_server.main()
        return 0

    if argv and argv[0] == "init":
        return _run_init(argv[1:])

    args = _build_analyze_parser().parse_args(argv)

    try:
        with discovery.resolve_target(args.target) as repo:
            cfg = _resolve_config(args, target_path=repo)

            patterns = list(cfg["filter"])
            if not cfg["no_default_filter"]:
                patterns.append(cfg["default_filter"])

            glob_keep = filtering.make_filter(patterns)
            keep = filtering.make_tracked_path_predicate(
                repo,
                glob_keep=glob_keep,
                ignore_directories=cfg["ignore_directories"],
                respect_gitignore=cfg["respect_gitignore"],
            )
            files = [f for f in discovery.list_tracked_files(repo) if keep(f)]
            score_metrics = list(cfg["score_metrics"])

            decay_half_life = cfg.get("decay_half_life")
            smell_weight = float(cfg.get("smell_weight", 0.0))
            
            show_progress = _want_progress(cfg)

            def _run_analysis(
                progress_cb: Callable[[str, int, int], None] | None,
            ) -> list[stats.Statistic]:
                return stats.build_block_stats(
                    repo,
                    files,
                    score_metrics,
                    since=cfg["since"],
                    until=cfg["until"],
                    workers=cfg["block_workers"],
                    decay_half_life=decay_half_life,
                    smell_weight=smell_weight,
                    progress_callback=progress_cb,
                    merged_config=cfg,
                    **stats.block_similarity_kwargs_from_config(cfg),
                )

            if show_progress:
                with progress_report.progress_runner(
                    True, description="Analyzing repository…"
                ) as cb:
                    results_full = _run_analysis(cb)
            else:
                results_full = _run_analysis(None)
            results = stats.sort_and_limit(
                results_full, by=cfg["sort"], limit=cfg["limit"]
            )
            if cfg["format"] == "json":
                payload: dict[str, object] = {
                    "results": [
                        output.statistic_to_output_dict(s, cfg) for s in results
                    ],
                    "cache": _block_cache.block_cache_stats(repo),
                }
                try:
                    payload["head_sha"] = RevisionCacheManager(repo).record_snapshot(
                        results_full
                    )
                except Exception:
                    logging.getLogger(__name__).debug(
                        "CLI JSON: revision snapshot not recorded",
                        exc_info=True,
                    )
                print(json.dumps(payload))
            else:
                print(output.render(results, cfg["format"], cfg))
            # JSON is a single object on stdout (``results`` + ``cache`` + optional ``head_sha``);
            # extra stdout after that breaks json.loads.
            if cfg["format"] != "json":
                for s in results:
                    if not s.score_subscores:
                        continue
                    band = str(s.score_band).lower()
                    if band not in ("high", "critical"):
                        continue
                    narrative = output.score_narrative_text(s, cfg)
                    if narrative:
                        print()
                        print(narrative)
        return 0
    except (NotADirectoryError, RuntimeError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
