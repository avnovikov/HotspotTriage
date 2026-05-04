"""CLI entry point. See `code-complexity-py --help` for usage."""
from __future__ import annotations

import argparse
import sys

from code_complexity_py import churn as _churn
from code_complexity_py import discovery, filtering, output, stats

DEFAULT_FILTER = "**/*.py"


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="code-complexity-py",
        description=(
            "Rank Python files by a composite score. Computes sloc, cyclomatic, "
            "halstead, maintainability and churn for every tracked .py file. "
            "Score = product of the metrics passed to -s."
        ),
    )
    p.add_argument("target", help="path to a local git repo, or a remote git URL")
    p.add_argument(
        "--filter",
        default="",
        help="comma-separated globs (AND semantics, '!' negates)",
    )
    p.add_argument(
        "--no-default-filter",
        action="store_true",
        help=f"disable the implicit default filter ({DEFAULT_FILTER})",
    )
    p.add_argument(
        "-s",
        "--score",
        default=",".join(stats.DEFAULT_SCORE_METRICS),
        help=(
            "comma-separated metrics whose product becomes the score. "
            f"Choose from: {', '.join(stats.SCORE_METRICS)}. "
            f"Default: {','.join(stats.DEFAULT_SCORE_METRICS)}"
        ),
    )
    p.add_argument("-f", "--format", choices=output.FORMATS, default="table")
    p.add_argument("-l", "--limit", type=int, default=None)
    p.add_argument("-i", "--since", default=None)
    p.add_argument("-u", "--until", default=None)
    p.add_argument("--sort", choices=stats.SORT_KEYS, default="score")
    p.add_argument("-d", "--directories", action="store_true")
    return p


def _split_csv(raw: str) -> list[str]:
    return [s for s in (p.strip() for p in raw.split(",")) if s]


def _validate_score_metrics(raw: str) -> list[str]:
    metrics = _split_csv(raw)
    if not metrics:
        raise ValueError("--score must list at least one metric")
    bad = [m for m in metrics if m not in stats.SCORE_METRICS]
    if bad:
        raise ValueError(
            f"unknown score metric(s): {bad} (valid: {list(stats.SCORE_METRICS)})"
        )
    return metrics


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        score_metrics = _validate_score_metrics(args.score)

        user_patterns = _split_csv(args.filter)
        patterns = list(user_patterns)
        if not args.no_default_filter:
            patterns.append(DEFAULT_FILTER)

        with discovery.resolve_target(args.target) as repo:
            keep = filtering.make_filter(patterns)
            files = [f for f in discovery.list_tracked_files(repo) if keep(f)]
            churn = _churn.compute_churn(repo, since=args.since, until=args.until)
            results = stats.build_stats(repo, files, churn, score_metrics)
            if args.directories:
                results = stats.aggregate_by_directory(results, score_metrics)
            results = stats.sort_and_limit(results, by=args.sort, limit=args.limit)
            print(output.render(results, args.format))
        return 0
    except (NotADirectoryError, RuntimeError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
