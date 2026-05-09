"""Generate comprehensive cache of codebase metrics.

Uses MCP ``analyze`` / ``cache_status`` for block metrics and cache stats;
class/method structure comes from :func:`extract_class_method_structure`.

This module provides a function to build a complete cache snapshot including:
- Block-level metrics (functions/methods) with churn data
- Class/method structure with line ranges
- Both cached for fast subsequent analysis

Usage:
    hotspottriage-cache [target] [--filter GLOBS] [--score METRICS]
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from hotspottriage import blocks as _blocks
from hotspottriage import config as _config
from hotspottriage import discovery, filtering

logger = logging.getLogger(__name__)


def extract_class_method_structure(
    target: str,
    filter: str | None = None,
    progress_callback: Callable[[str, int, int], None] | None = None,
) -> list[dict[str, Any]]:
    """Build file/class/method line-range rows (used by cache generation, not MCP)."""
    cfg = _config.DEFAULTS.copy()
    if filter:
        cfg["filter"] = [f.strip() for f in filter.split(",")]

    with discovery.resolve_target(target) as repo:
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
        n_files = len(files)

        results: list[dict[str, Any]] = []
        for idx, file_path in enumerate(files, start=1):
            if progress_callback:
                progress_callback(f"Indexing {file_path}", idx, n_files)
            full_path = repo / file_path
            try:
                src = full_path.read_text(encoding="utf-8")
                blocks = _blocks.extract_blocks(src)

                for block in blocks:
                    parts = block.name.split(".")
                    if len(parts) > 1:
                        class_name = parts[0] if len(parts) >= 1 else None
                        method_name = parts[-1]
                    else:
                        class_name = None
                        method_name = parts[0]

                    results.append({
                        "file": str(file_path),
                        "class": class_name,
                        "method": method_name,
                        "full_name": block.name,
                        "start_line": block.start,
                        "end_line": block.end,
                        "lines": block.end - block.start + 1,
                    })
            except Exception as e:
                logger.warning("Failed to analyze %s: %s", file_path, e)

    return results


def generate_full_cache(
    target: str,
    filter: str | None = None,
    score_metrics: str = "churn_per_sloc,cyclomatic",
    verbose: bool = False,
    progress_callback: Callable[[str, int, int], None] | None = None,
    config_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate comprehensive cache for entire codebase.

    Creates a complete snapshot including:
    - Block-level metrics (cached in .hotspottriage/cache/blocks.pkl)
    - Class/method structure analysis
    - Cache statistics and metadata

    Args:
        target: Path to git repository
        filter: Comma-separated glob patterns (optional)
        score_metrics: Metrics to compute score from
        verbose: Print progress information
        progress_callback: Optional ``(label, done, total)`` updates (e.g. dashboard job UI)
        config_overrides: Optional scoring/config values to merge before analysis

    Returns:
        Dictionary with:
        - blocks: Block-level cache stats
        - classes: Class/method structure
        - cache_status: Cache statistics
        - metadata: Generation info
    """
    if verbose:
        print(f"🔄 Generating cache for {target}...")

    result = {
        "timestamp": None,
        "target": target,
        "filter": filter,
        "score_metrics": score_metrics,
    }

    try:
        if progress_callback:
            progress_callback("Starting cache generation", 0, 1)
        # Step 1: Initialize repository cache (blocks + churn)
        if verbose:
            print("  📊 Initializing block-level cache...")
        if progress_callback:
            progress_callback("Initializing block-level cache", 0, 1)
        try:
            from hotspottriage import mcp_server as _mcp_server

            blocks_data = _mcp_server.run_cached_block_analysis_dict(
                target=target,
                filter=filter,
                score_metrics=score_metrics,
                compact=False,
                similarity=True,
                progress_callback=progress_callback,
                config_overrides=config_overrides,
            )
        except Exception as e:
            result["blocks"] = {"error": str(e)}
        else:
            result["blocks"] = {
                "count": len(blocks_data.get("results", [])),
                "cache": blocks_data.get("cache", {}),
                "results": blocks_data.get("results", []),
            }
            if verbose:
                print(f"    ✓ Cached {result['blocks']['count']} blocks")

        # Step 2: Analyze class/method structure
        if verbose:
            print("  🏛️  Analyzing class/method structure...")
        if progress_callback:
            progress_callback("Analyzing class/method structure", 0, 1)
        try:
            classes_data = extract_class_method_structure(
                target, filter=filter, progress_callback=progress_callback
            )
        except Exception as e:
            result["classes"] = {"error": str(e)}
        else:
            result["classes"] = {
                "count": len(classes_data),
                "results": classes_data,
            }
            if verbose:
                print(f"    ✓ Indexed {result['classes']['count']} classes/methods")

        # Step 3: Get cache status
        if verbose:
            print("  📁 Checking cache status...")
        if progress_callback:
            progress_callback("Checking cache status", 0, 1)
        from hotspottriage import mcp_server as _mcp_server

        status_result = _mcp_server.cache_status(target=target)
        status_data = json.loads(status_result)

        result["cache_status"] = status_data
        if verbose:
            print(f"    ✓ Cache: {status_data.get('entries', 0)} entries, "
                  f"{status_data.get('size_bytes', 0)} bytes")

        # Step 4: Generate statistics
        result["metadata"] = {
            "status": "success",
            "blocks_cached": result["blocks"].get("count", 0),
            "classes_indexed": result["classes"].get("count", 0),
            "total_cache_entries": status_data.get("entries", 0),
            "cache_size_mb": round(status_data.get("size_bytes", 0) / (1024 * 1024), 2),
        }
        if progress_callback:
            progress_callback("Cache generation complete", 1, 1)

        if verbose:
            print(f"\n✅ Cache generation complete!")
            print(f"   Blocks: {result['metadata']['blocks_cached']}")
            print(f"   Classes/Methods: {result['metadata']['classes_indexed']}")
            print(f"   Cache size: {result['metadata']['cache_size_mb']} MB")

    except Exception as e:
        logger.exception("Cache generation failed")
        result["metadata"] = {
            "status": "error",
            "error": str(e),
        }
        if verbose:
            print(f"❌ Error: {e}")

    return result


def print_cache_summary(cache_data: dict[str, Any]) -> None:
    """Print a formatted summary of cache data.

    Args:
        cache_data: Result from generate_full_cache()
    """
    metadata = cache_data.get("metadata", {})
    status = metadata.get("status", "unknown")

    print("\n" + "=" * 60)
    print("CACHE GENERATION SUMMARY")
    print("=" * 60)
    print(f"Status: {status}")
    print(f"Target: {cache_data.get('target')}")
    print(f"Filter: {cache_data.get('filter') or '(default)'}")
    print(f"Score metrics: {cache_data.get('score_metrics')}")
    print()

    if status == "success":
        print("📊 BLOCK-LEVEL METRICS")
        blocks = cache_data.get("blocks", {})
        print(f"  Blocks analyzed: {blocks.get('count', 0)}")
        if blocks.get("results"):
            sample = blocks["results"][0]
            print(f"  Sample: {sample.get('path')} - score: {sample.get('score', 'N/A')}")

        print("\n🏛️  CLASS/METHOD STRUCTURE")
        classes = cache_data.get("classes", {})
        print(f"  Classes/methods indexed: {classes.get('count', 0)}")
        if classes.get("results"):
            sample = classes["results"][0]
            print(f"  Sample: {sample.get('full_name')} in {sample.get('file')}")

        print("\n📁 CACHE STATUS")
        cache_status = cache_data.get("cache_status", {})
        print(f"  Cache dir: {cache_status.get('cache_dir')}")
        print(f"  Entries: {cache_status.get('entries', 0)}")
        print(f"  Size: {cache_status.get('size_bytes', 0)} bytes")

        print("\n📈 STATISTICS")
        for key, value in metadata.items():
            if key != "status":
                print(f"  {key}: {value}")
    else:
        error = metadata.get("error", "Unknown error")
        print(f"Error: {error}")

    print("=" * 60 + "\n")


def main() -> int:
    """CLI entry point for cache generation."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="hotspottriage-cache",
        description="Generate comprehensive codebase cache (blocks + class/method structure)",
    )
    parser.add_argument("target", nargs="?", default=".", help="git repository path")
    parser.add_argument(
        "--filter",
        help="comma-separated glob patterns (AND semantics)",
    )
    parser.add_argument(
        "-s",
        "--score",
        default="churn_per_sloc,cyclomatic",
        help="metrics for score computation (default: churn_per_sloc,cyclomatic)",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="suppress progress output",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="output raw JSON instead of formatted summary",
    )

    args = parser.parse_args()

    try:
        cache_data = generate_full_cache(
            target=args.target,
            filter=args.filter,
            score_metrics=args.score,
            verbose=not args.quiet,
        )

        if args.json:
            print(json.dumps(cache_data, indent=2))
        else:
            print_cache_summary(cache_data)

        # Return success if cache generation succeeded
        return 0 if cache_data.get("metadata", {}).get("status") == "success" else 1

    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
